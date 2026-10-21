from datetime import date
from types import SimpleNamespace

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .models import Assignment, Dispatch, History, Item
from . import services
from .views import _apply_initial_status


INVENTORY_PERMS = ['add_item', 'change_item', 'add_assignment', 'change_assignment',
                   'add_dispatch', 'change_dispatch', 'add_reservation', 'change_reservation']


def grant_inventory_perms(user):
    """The permissions an inventory manager has (the views now check these)."""
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label='inventory', codename__in=INVENTORY_PERMS))
    return User.objects.get(pk=user.pk)  # fresh instance: permission cache


class ReturnWorkflowTests(TestCase):
    def setUp(self):
        self.staff_user = grant_inventory_perms(User.objects.create_user('staff', password='pw', is_staff=True))
        self.worker = User.objects.create_user('worker', password='pw')
        self.client.force_login(self.staff_user)

        self.tool = Item.objects.create(
            item_type='TOOL', name='Drill', serial_number='SN-1', status='ASSIGNED'
        )
        self.assignment = Assignment.objects.create(
            item=self.tool, assigned_to=self.worker, assigned_by=self.staff_user,
            assignment_date=date.today()
        )

    def test_return_assignment_good_condition_makes_item_available(self):
        url = reverse('inventory-return-assignment', kwargs={'pk': self.assignment.pk})
        response = self.client.post(url, {'condition': 'GOOD', 'return_notes': ''})
        self.assertEqual(response.status_code, 302)

        self.tool.refresh_from_db()
        self.assignment.refresh_from_db()
        self.assertEqual(self.tool.status, 'AVAILABLE')
        self.assertEqual(self.tool.location, 'Warehouse')
        self.assertEqual(self.assignment.return_condition, 'GOOD')
        self.assertIsNotNone(self.assignment.return_date)
        self.assertTrue(History.objects.filter(item=self.tool, action='RETURNED').exists())

    def test_return_assignment_damaged_requires_notes(self):
        url = reverse('inventory-return-assignment', kwargs={'pk': self.assignment.pk})
        response = self.client.post(url, {'condition': 'DAMAGED', 'return_notes': ''})
        self.assertEqual(response.status_code, 200)  # form error, re-rendered
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'ASSIGNED')  # unchanged

    def test_return_assignment_damaged_sends_to_maintenance(self):
        url = reverse('inventory-return-assignment', kwargs={'pk': self.assignment.pk})
        response = self.client.post(url, {'condition': 'DAMAGED', 'return_notes': 'Cracked casing'})
        self.assertEqual(response.status_code, 302)

        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'MAINTENANCE')
        self.assertTrue(History.objects.filter(item=self.tool, action='MAINTENANCE').exists())

    def test_return_assignment_lost_retires_item(self):
        url = reverse('inventory-return-assignment', kwargs={'pk': self.assignment.pk})
        response = self.client.post(url, {'condition': 'LOST', 'return_notes': 'Never came back'})
        self.assertEqual(response.status_code, 302)

        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'RETIRED')

    def test_return_dispatch_good_condition(self):
        self.tool.status = 'DISPATCHED'
        self.tool.save()
        self.assignment.delete()
        dispatch = Dispatch.objects.create(
            item=self.tool, project='Site A', dispatched_by=self.staff_user,
            dispatch_date=date.today()
        )
        url = reverse('inventory-return-dispatch', kwargs={'pk': dispatch.pk})
        response = self.client.post(url, {'condition': 'GOOD', 'return_notes': ''})
        self.assertEqual(response.status_code, 302)

        self.tool.refresh_from_db()
        dispatch.refresh_from_db()
        self.assertEqual(self.tool.status, 'AVAILABLE')
        self.assertIsNotNone(dispatch.return_date)

    def test_material_dispatch_has_no_return_route(self):
        material = Item.objects.create(
            item_type='MATERIAL', name='Cement', serial_number='SN-2', quantity=10
        )
        dispatch = Dispatch.objects.create(
            item=material, project='Site A', dispatched_by=self.staff_user,
            dispatch_date=date.today(), quantity=5
        )
        url = reverse('inventory-return-dispatch', kwargs={'pk': dispatch.pk})
        response = self.client.post(url, {'condition': 'GOOD', 'return_notes': ''})
        self.assertEqual(response.status_code, 404)


class BulkUpdatePermissionTests(TestCase):
    def setUp(self):
        self.staff_user = grant_inventory_perms(User.objects.create_user('staff2', password='pw', is_staff=True))
        self.worker = User.objects.create_user('worker2', password='pw')
        self.item = Item.objects.create(item_type='TOOL', name='Hammer', serial_number='SN-3')

    def test_non_staff_cannot_bulk_update(self):
        self.client.force_login(self.worker)
        url = reverse('inventory-bulk-update')
        response = self.client.post(
            url, data='{"item_ids": [%d], "action": "retire"}' % self.item.pk,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'AVAILABLE')

    def test_staff_can_retire(self):
        self.client.force_login(self.staff_user)
        url = reverse('inventory-bulk-update')
        response = self.client.post(
            url, data='{"item_ids": [%d], "action": "retire"}' % self.item.pk,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'RETIRED')

    def test_delete_action_no_longer_supported(self):
        self.client.force_login(self.staff_user)
        url = reverse('inventory-bulk-update')
        response = self.client.post(
            url, data='{"item_ids": [%d], "action": "delete"}' % self.item.pk,
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())


class MaterialAssignmentTests(TestCase):
    """Materials are assignable to a user on a returnable basis, drawn down/restored by quantity."""

    def setUp(self):
        self.staff_user = User.objects.create_user('staff3', password='pw', is_staff=True)
        self.worker = User.objects.create_user('worker3', password='pw')
        self.material = Item.objects.create(
            item_type='MATERIAL', name='Cable Reel', serial_number='SN-10', quantity=20
        )

    def _assign(self, quantity=5):
        assignment = Assignment.objects.create(
            item=self.material, quantity=quantity, assigned_to=self.worker, assigned_by=self.staff_user,
            assignment_date=date.today()
        )
        self.material.quantity -= quantity
        self.material.save()
        return assignment

    def test_assigning_material_draws_down_stock_without_flipping_item_status(self):
        self._assign(5)
        self.material.refresh_from_db()
        self.assertEqual(self.material.quantity, 15)
        self.assertEqual(self.material.status, 'AVAILABLE')

    def test_good_condition_return_restores_material_stock(self):
        assignment = self._assign(5)
        services.process_return(
            assignment, condition='GOOD', return_notes='', performed_by=self.staff_user,
            details_prefix='Returned by worker3'
        )
        self.material.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(self.material.quantity, 20)
        self.assertEqual(self.material.status, 'AVAILABLE')
        self.assertIsNotNone(assignment.return_date)

    def test_damaged_condition_return_does_not_restock_material(self):
        assignment = self._assign(5)
        services.process_return(
            assignment, condition='DAMAGED', return_notes='Wet and unusable', performed_by=self.staff_user,
            details_prefix='Returned by worker3'
        )
        self.material.refresh_from_db()
        self.assertEqual(self.material.quantity, 15)


class AssignFormMaterialQuerysetTests(TestCase):
    def test_material_with_stock_is_selectable_zero_stock_is_not(self):
        from .forms import AssignForm

        in_stock = Item.objects.create(
            item_type='MATERIAL', name='Pipe', serial_number='SN-20', quantity=3, status='AVAILABLE'
        )
        out_of_stock = Item.objects.create(
            item_type='MATERIAL', name='Wire', serial_number='SN-21', quantity=0, status='AVAILABLE'
        )
        queryset = AssignForm().fields['item'].queryset
        self.assertIn(in_stock, queryset)
        self.assertNotIn(out_of_stock, queryset)


class ItemTypeChoicesTests(TestCase):
    def test_new_categories_are_available(self):
        codes = dict(Item.ITEM_TYPES)
        for expected in ('TOOL', 'IT_ASSET', 'MATERIAL', 'SOFTWARE_LICENSE', 'OTHER'):
            self.assertIn(expected, codes)


class InitialStatusOnCreateTests(TestCase):
    """New items can be entered directly as Assigned/Dispatched/Consumed/Under Maintenance."""

    def setUp(self):
        self.staff_user = User.objects.create_user('staff4', password='pw', is_staff=True)
        self.worker = User.objects.create_user('worker4', password='pw')

    def _fake_form(self, cleaned_data):
        return SimpleNamespace(cleaned_data=cleaned_data)

    def test_assigned_tool_creates_assignment_and_sets_location(self):
        tool = Item.objects.create(item_type='TOOL', name='Grinder', serial_number='SN-30', status='ASSIGNED')
        form = self._fake_form({
            'assigned_to': self.worker,
            'assignment_date': date.today(),
            'assignment_return_date': None,
            'assignment_notes': '',
        })
        _apply_initial_status(tool, form, SimpleNamespace(user=self.staff_user))

        tool.refresh_from_db()
        assignment = Assignment.objects.get(item=tool)
        self.assertEqual(assignment.assigned_to, self.worker)
        self.assertEqual(assignment.quantity, 1)
        self.assertEqual(tool.status, 'ASSIGNED')
        self.assertIn('worker4', tool.location)

    def test_assigned_material_draws_down_stock_and_stays_available(self):
        material = Item.objects.create(item_type='MATERIAL', name='Rope', serial_number='SN-31',
                                        quantity=30, status='ASSIGNED')
        form = self._fake_form({
            'assigned_to': self.worker,
            'assignment_date': date.today(),
            'assignment_return_date': None,
            'assignment_notes': '',
        })
        _apply_initial_status(material, form, SimpleNamespace(user=self.staff_user))

        material.refresh_from_db()
        assignment = Assignment.objects.get(item=material)
        self.assertEqual(assignment.quantity, 30)
        self.assertEqual(material.quantity, 0)
        self.assertEqual(material.status, 'AVAILABLE')

    def test_dispatched_tool_creates_dispatch_record(self):
        tool = Item.objects.create(item_type='TOOL', name='Ladder', serial_number='SN-32', status='DISPATCHED')
        form = self._fake_form({
            'dispatch_project': 'Site B',
            'dispatch_site_location': 'Bay 3',
            'dispatch_responsible_person': self.worker,
            'dispatch_date': date.today(),
            'dispatch_return_date': None,
            'dispatch_notes': '',
        })
        _apply_initial_status(tool, form, SimpleNamespace(user=self.staff_user))

        tool.refresh_from_db()
        dispatch = Dispatch.objects.get(item=tool)
        self.assertEqual(dispatch.project, 'Site B')
        self.assertEqual(tool.status, 'DISPATCHED')

    def test_consumed_material_creates_dispatch_and_zeroes_stock(self):
        material = Item.objects.create(item_type='MATERIAL', name='Sand', serial_number='SN-33',
                                        quantity=12, status='CONSUMED')
        form = self._fake_form({
            'dispatch_project': 'Site C',
            'dispatch_site_location': '',
            'dispatch_responsible_person': self.worker,
            'dispatch_date': date.today(),
            'dispatch_return_date': None,
            'dispatch_notes': '',
        })
        _apply_initial_status(material, form, SimpleNamespace(user=self.staff_user))

        material.refresh_from_db()
        dispatch = Dispatch.objects.get(item=material)
        self.assertEqual(dispatch.quantity, 12)
        self.assertEqual(material.quantity, 0)
        self.assertEqual(material.status, 'CONSUMED')

    def test_maintenance_returns_history_detail(self):
        tool = Item.objects.create(item_type='TOOL', name='Saw', serial_number='SN-34', status='MAINTENANCE')
        form = self._fake_form({'maintenance_notes': 'Blade is bent'})
        detail = _apply_initial_status(tool, form, SimpleNamespace(user=self.staff_user))
        self.assertIn('Blade is bent', detail)

    def test_available_status_needs_no_extra_fields(self):
        tool = Item.objects.create(item_type='TOOL', name='Wrench', serial_number='SN-35', status='AVAILABLE')
        detail = _apply_initial_status(tool, self._fake_form({}), SimpleNamespace(user=self.staff_user))
        self.assertIsNone(detail)
        self.assertFalse(Assignment.objects.filter(item=tool).exists())
        self.assertFalse(Dispatch.objects.filter(item=tool).exists())


class ItemFormStatusValidationTests(TestCase):
    """ItemForm requires the right extra fields once a non-Available initial status is picked."""

    def _base_data(self, **overrides):
        data = {
            'item_type': 'TOOL', 'name': 'Impact Driver', 'serial_number': 'SN-40',
            'quantity': 1, 'min_quantity': 0, 'status': 'AVAILABLE',
        }
        data.update(overrides)
        return data

    def test_assigned_without_assignee_is_invalid(self):
        from .forms import ItemForm
        form = ItemForm(data=self._base_data(status='ASSIGNED'))
        self.assertFalse(form.is_valid())
        self.assertIn('assigned_to', form.errors)

    def test_maintenance_without_reason_is_invalid(self):
        from .forms import ItemForm
        form = ItemForm(data=self._base_data(status='MAINTENANCE'))
        self.assertFalse(form.is_valid())
        self.assertIn('maintenance_notes', form.errors)

    def test_available_status_does_not_require_extra_fields(self):
        from .forms import ItemForm
        form = ItemForm(data=self._base_data(status='AVAILABLE'))
        self.assertTrue(form.is_valid(), form.errors)


class StatusIntegrityTests(TestCase):
    """An item's status and its open assignment/dispatch records must always agree."""

    def setUp(self):
        self.manager = grant_inventory_perms(User.objects.create_user('mgr', password='pw', is_staff=True))
        self.alice = User.objects.create_user('alice', first_name='Alice', last_name='A')
        self.bob = User.objects.create_user('bob', first_name='Bob', last_name='B')
        self.tool = Item.objects.create(item_type='TOOL', name='Meter', serial_number='M-1')
        self.client.force_login(self.manager)

    def open_holders(self, item):
        return list(item.open_assignments().values_list('assigned_to__username', flat=True))

    def test_edit_cannot_make_an_assigned_item_available(self):
        services.assign_item(self.tool, self.alice, self.manager, date.today())
        form_data = {'item_type': 'TOOL', 'name': 'Meter', 'serial_number': 'M-1', 'quantity': 1,
                     'min_quantity': 0, 'status': 'AVAILABLE', 'location': 'Shelf'}
        self.client.post(reverse('inventory-item-update', args=[self.tool.pk]), form_data)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'ASSIGNED')
        self.assertEqual(self.open_holders(self.tool), ['alice'])

    def test_a_tool_is_never_held_by_two_people(self):
        services.assign_item(self.tool, self.alice, self.manager, date.today())
        services.assign_item(self.tool, self.bob, self.manager, date.today())  # transfer
        self.assertEqual(self.open_holders(self.tool), ['bob'])
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'ASSIGNED')

    def test_transfer_closes_every_stale_holder(self):
        # damaged data from before the fix: item Available with an open assignment
        Assignment.objects.create(item=self.tool, assigned_to=self.alice, assigned_by=self.manager,
                                  assignment_date=date.today())
        services.assign_item(self.tool, self.bob, self.manager, date.today())
        self.assertEqual(self.open_holders(self.tool), ['bob'])

    def test_returning_one_of_two_holders_keeps_item_assigned(self):
        for who in (self.alice, self.bob):  # damaged data: two open assignments
            Assignment.objects.create(item=self.tool, assigned_to=who, assigned_by=self.manager,
                                      assignment_date=date.today())
        self.tool.status = 'ASSIGNED'
        self.tool.save()
        stale = Assignment.objects.get(item=self.tool, assigned_to=self.alice)
        services.process_return(stale, 'GOOD', '', self.manager, 'Returned by Alice')
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'ASSIGNED')  # Bob still has it

    def test_return_twice_is_refused(self):
        a, _ = services.assign_item(self.tool, self.alice, self.manager, date.today())
        services.process_return(a, 'GOOD', '', self.manager, 'x')
        with self.assertRaises(services.InventoryError):
            services.process_return(a, 'GOOD', '', self.manager, 'x')

    def test_bulk_retire_refuses_items_still_out(self):
        services.assign_item(self.tool, self.alice, self.manager, date.today())
        self.client.post(reverse('inventory-bulk-update'), data='{"item_ids": [%d], "action": "retire"}' % self.tool.pk,
                         content_type='application/json')
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'ASSIGNED')
        self.assertEqual(self.open_holders(self.tool), ['alice'])

    def test_dispatched_it_asset_can_be_returned(self):
        laptop = Item.objects.create(item_type='IT_ASSET', name='Laptop', serial_number='L-1')
        services.dispatch_item(laptop, 'Site X', '', self.alice, self.manager, date.today())
        dispatch = Dispatch.objects.get(item=laptop)
        response = self.client.post(reverse('inventory-return-dispatch', args=[dispatch.pk]),
                                    {'condition': 'GOOD', 'return_notes': ''})
        self.assertEqual(response.status_code, 302)
        laptop.refresh_from_db()
        self.assertEqual(laptop.status, 'AVAILABLE')

    def test_assign_page_does_not_crash_when_status_and_records_disagree(self):
        self.tool.status = 'ASSIGNED'  # no open assignment at all
        self.tool.save()
        response = self.client.post(reverse('inventory-assign-create'), {
            'item': self.tool.pk, 'quantity': 1, 'assigned_to': self.bob.pk, 'assignment_date': date.today().isoformat()})
        self.assertLess(response.status_code, 500)

    def test_material_return_twice_does_not_double_stock(self):
        cable = Item.objects.create(item_type='MATERIAL', name='Cable', serial_number='C-1', quantity=10)
        a, _ = services.assign_item(cable, self.alice, self.manager, date.today(), quantity=4)
        services.process_return(a, 'GOOD', '', self.manager, 'x')
        with self.assertRaises(services.InventoryError):
            services.process_return(a, 'GOOD', '', self.manager, 'x')
        cable.refresh_from_db()
        self.assertEqual(cable.quantity, 10)


class PermissionTests(TestCase):
    def setUp(self):
        self.manager = grant_inventory_perms(User.objects.create_user('mgr2', password='pw', is_staff=True))
        self.outsider = User.objects.create_user('outsider', password='pw')  # logged in, no inventory rights
        self.tool = Item.objects.create(item_type='TOOL', name='Gauge', serial_number='G-1')
        self.assignment, _ = services.assign_item(self.tool, self.manager, self.manager, date.today())
        self.client.force_login(self.outsider)

    def test_outsider_cannot_edit_items(self):
        response = self.client.post(reverse('inventory-item-update', args=[self.tool.pk]), {'name': 'x'})
        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_return_someone_elses_item(self):
        response = self.client.post(reverse('inventory-return-assignment', args=[self.assignment.pk]),
                                    {'condition': 'LOST', 'return_notes': 'x'})
        self.assertEqual(response.status_code, 403)
        self.assignment.refresh_from_db()
        self.assertIsNone(self.assignment.return_date)

    def test_outsider_cannot_reserve(self):
        response = self.client.get(reverse('inventory-reservation-create'))
        self.assertEqual(response.status_code, 403)


class NamingAndPagesTests(TestCase):
    def setUp(self):
        from employees.models import Employee
        from gap_analysis.models import SkillMatrix
        self.manager = grant_inventory_perms(
            User.objects.create_user('mgr3', password='pw', is_staff=True, is_superuser=True))
        self.login = User.objects.create_user('darshan', first_name='Darshan', last_name='Pardeshi')
        employee = Employee.objects.create(name='Darshan Dharmendrasingh  Pardeshi', is_active=True)
        SkillMatrix.objects.update_or_create(employee=employee, defaults={'user': self.login})
        self.client.force_login(self.manager)

    def test_person_name_is_the_employee_name(self):
        from .people import person_name
        self.assertEqual(person_name(User.objects.get(pk=self.login.pk)), 'Darshan Dharmendrasingh Pardeshi')

    def test_dispatch_admin_search_works(self):
        response = self.client.get('/admin/inventory/dispatch/?q=abc')
        self.assertEqual(response.status_code, 200)

    def test_history_pager_keeps_filters(self):
        tool = Item.objects.create(item_type='TOOL', name='Probe', serial_number='P-1')
        for i in range(30):
            History.objects.create(item=tool, action='UPDATED', user=self.manager, details=f'n{i}')
        response = self.client.get(reverse('inventory-history-list'), {'action': 'UPDATED'})
        self.assertContains(response, 'action=UPDATED&amp;page=2')

    def test_sync_command_runs(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('sync_employee_users', '--dry-run', stdout=out)
        self.assertIn('DRY RUN', out.getvalue())
