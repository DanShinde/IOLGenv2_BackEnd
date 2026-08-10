from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Assignment, Dispatch, History, Item


class ReturnWorkflowTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user('staff', password='pw', is_staff=True)
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
        self.staff_user = User.objects.create_user('staff2', password='pw', is_staff=True)
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
