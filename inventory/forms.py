from datetime import date, timedelta
from django import forms
from django.contrib.auth.models import User
from .models import Item, History, Reservation, RETURN_CONDITION_CHOICES
from django.core.exceptions import ValidationError


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'item_type', 'name', 'model', 'serial_number', 'make',
            'description', 'image', 'purchase_date', 'purchase_cost',
            'quantity', 'min_quantity', 'location', 'category', 'status', 'remarks'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3,
                                            'placeholder': 'Any notes, updates, or important information...'}),
            'remarks': forms.Textarea(attrs={'rows': 3,
                                            'placeholder': 'Any notes, updates, or important information...'}),
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'purchase_cost': forms.NumberInput(attrs={'step': '0.01'}),
            'item_type': forms.Select(),
            'status': forms.Select(),
        }
        help_texts = {
            'serial_number': 'Unique identifier for tracking',
            'quantity': 'For materials: stock quantity. For tools: always 1',
            'min_quantity': 'Alert when stock falls below this level',
            'location': 'Current physical location',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add styling to all fields
        for field_name, field in self.fields.items():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'

    def clean_serial_number(self):
        serial_number = self.cleaned_data['serial_number']
        if self.instance.pk is None:  # Only check for new items
            if Item.objects.filter(serial_number=serial_number).exists():
                raise ValidationError('An item with this serial number already exists.')
        return serial_number


class ItemFilterForm(forms.Form):
    ITEM_TYPE_CHOICES = [('', 'All Types')] + Item.ITEM_TYPES
    STATUS_CHOICES = [('', 'All Status')] + Item.STATUS_CHOICES

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md',
            'placeholder': 'Search by name, serial number, make, or model...'
        })
    )
    item_type = forms.ChoiceField(
        choices=ITEM_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'})
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-md'})
    )


class HistoryFilterForm(forms.Form):
    ACTION_CHOICES = [('', 'All Actions')] + History.ACTION_CHOICES
    ITEM_TYPE_CHOICES = [('', 'All Types')] + Item.ITEM_TYPES

    action = forms.ChoiceField(choices=ACTION_CHOICES, required=False,
                               widget=forms.Select())
    item_type = forms.ChoiceField(choices=ITEM_TYPE_CHOICES, required=False,
                                  widget=forms.Select())
    item = forms.ModelChoiceField(
        queryset=Item.objects.all().order_by('name'),
        required=False,
        empty_label='All Items',
        widget=forms.Select()
    )
    date_from = forms.DateField(required=False,
                                widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False,
                              widget=forms.DateInput(attrs={'type': 'date'}))
    serial_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Search by serial number...'})
    )
    user_search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Search by username...'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Search in details...'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'


class ReturnForm(forms.Form):
    """Captures the condition a tool is in when it's returned from an assignment or dispatch"""
    condition = forms.ChoiceField(
        choices=RETURN_CONDITION_CHOICES,
        initial='GOOD',
        widget=forms.RadioSelect,
        label="Condition on Return"
    )
    return_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Describe any damage or issues (required if not returned in good condition)...'
        }),
        label="Notes"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.fields['return_notes'].widget.attrs.get('class'):
            self.fields['return_notes'].widget.attrs['class'] = 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'

    def clean(self):
        cleaned_data = super().clean()
        condition = cleaned_data.get('condition')
        return_notes = cleaned_data.get('return_notes')
        if condition in ('DAMAGED', 'NEEDS_REPAIR', 'LOST') and not return_notes:
            self.add_error('return_notes', 'Please describe what happened.')
        return cleaned_data


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ['item', 'reserved_for', 'start_date', 'end_date', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'What is this tool needed for?'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = Item.objects.filter(item_type='TOOL').exclude(status='RETIRED').order_by('name')
        self.fields['reserved_for'].queryset = User.objects.filter(is_active=True).order_by('username')

        for field_name, field in self.fields.items():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'

        self.fields['item'].label_from_instance = lambda item: f"{item.name} ({item.serial_number})"
        self.fields['reserved_for'].label_from_instance = lambda user: (
            f"{user.get_full_name()} ({user.username})" if user.get_full_name() else user.username
        )

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})

        if item and start_date and end_date:
            conflicts = Reservation.objects.filter(item=item, status='PENDING')
            if self.instance.pk:
                conflicts = conflicts.exclude(pk=self.instance.pk)
            for existing in conflicts:
                if existing.overlaps(start_date, end_date):
                    who = existing.reserved_for.get_full_name() or existing.reserved_for.username
                    raise ValidationError(
                        f'{item.name} is already reserved for {who} from {existing.start_date} to {existing.end_date}.'
                    )
        return cleaned_data


def _assignable_tool_label(item):
    label = f"{item.name} ({item.serial_number})"
    if item.status == 'ASSIGNED':
        active = item.assignments.filter(return_date__isnull=True).first()
        if active:
            who = active.assigned_to.get_full_name() or active.assigned_to.username
            label += f" - currently with {who}"
    return label


class AssignForm(forms.Form):
    """Assign an available tool to a user, or transfer an already-assigned tool to someone else"""
    item = forms.ModelChoiceField(
        queryset=Item.objects.filter(item_type='TOOL', status__in=['AVAILABLE', 'ASSIGNED']).order_by('name'),
        label="Tool",
        widget=forms.Select(),
    )
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        label="Assign To",
        widget=forms.Select(),
    )
    assignment_date = forms.DateField(
        initial=date.today,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Date"
    )
    expected_return_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Expected Return Date"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Notes...'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'

        self.fields['item'].label_from_instance = _assignable_tool_label
        self.fields['assigned_to'].label_from_instance = lambda user: (
            f"{user.get_full_name()} ({user.username})" if user.get_full_name() else user.username
        )

        if not self.initial.get('expected_return_date'):
            self.initial['expected_return_date'] = (date.today() + timedelta(days=7)).isoformat()

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        assigned_to = cleaned_data.get('assigned_to')
        assignment_date = cleaned_data.get('assignment_date')
        expected_return_date = cleaned_data.get('expected_return_date')

        if expected_return_date and assignment_date and expected_return_date < assignment_date:
            self.add_error('expected_return_date', 'Return date cannot be before assignment date.')

        if item and item.status == 'ASSIGNED' and assigned_to:
            active_assignment = item.assignments.filter(return_date__isnull=True).first()
            if active_assignment and active_assignment.assigned_to == assigned_to:
                raise ValidationError('This tool is already assigned to that user.')

        # Don't let a direct assignment silently override someone else's pending reservation
        if item and assigned_to and assignment_date:
            conflict_end = expected_return_date or assignment_date
            conflicting = Reservation.objects.filter(item=item, status='PENDING').exclude(reserved_for=assigned_to)
            for reservation in conflicting:
                if reservation.overlaps(assignment_date, conflict_end):
                    who = reservation.reserved_for.get_full_name() or reservation.reserved_for.username
                    raise ValidationError(
                        f'{item.name} is reserved for {who} from {reservation.start_date} to {reservation.end_date}. '
                        f'Fulfill or cancel that reservation first.'
                    )

        return cleaned_data


class DispatchForm(forms.Form):
    """Dispatch a tool or material to a project"""
    item = forms.ModelChoiceField(
        queryset=Item.objects.filter(status__in=['AVAILABLE', 'ASSIGNED']).order_by('name'),
        label="Item",
        widget=forms.Select(),
    )
    project = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Project name'}),
        label="Project Name"
    )
    site_location = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Site location'}),
        label="Site Location"
    )
    responsible_person = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Who at the site is responsible for this item?'}),
        label="Responsible Person",
        help_text="Needed to recover the item later - required even for materials."
    )
    quantity = forms.IntegerField(
        required=False,
        initial=1,
        min_value=1,
        widget=forms.NumberInput(attrs={'placeholder': '1'}),
        label="Quantity",
        help_text="For materials only - how many units to dispatch"
    )
    dispatch_date = forms.DateField(
        initial=date.today,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Dispatch Date"
    )
    expected_return_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Only for tools - materials won't return"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Notes...'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'

        self.fields['item'].label_from_instance = lambda item: (
            f"{item.name} ({item.serial_number}) - {item.get_item_type_display()}"
        )

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        quantity = cleaned_data.get('quantity') or 1
        dispatch_date = cleaned_data.get('dispatch_date')
        expected_return_date = cleaned_data.get('expected_return_date')

        if item and item.item_type == 'MATERIAL' and quantity > item.quantity:
            raise ValidationError(f'Cannot dispatch {quantity} units. Only {item.quantity} available.')

        if dispatch_date and expected_return_date and expected_return_date < dispatch_date:
            self.add_error('expected_return_date', 'Return date cannot be before dispatch date.')

        return cleaned_data
