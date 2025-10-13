from datetime import date, timedelta
from django import forms
from django.contrib.auth.models import User
from .models import Item, Assignment, Dispatch, History
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
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'rows': 3, 'class': 'form-control',
                                            'placeholder': 'Any notes, updates, or important information...'}),
            'purchase_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'purchase_cost': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
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
                               widget=forms.Select(attrs={'class': 'form-control'}))
    item_type = forms.ChoiceField(choices=ITEM_TYPE_CHOICES, required=False,
                                  widget=forms.Select(attrs={'class': 'form-control'}))
    item = forms.ModelChoiceField(
        queryset=Item.objects.all().order_by('name'),
        required=False,
        empty_label='All Items',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    date_from = forms.DateField(required=False,
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    date_to = forms.DateField(required=False,
                              widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    serial_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by serial number...'})
    )
    user_search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by username...'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search in details...'})
    )


class UnifiedTransferForm(forms.Form):
    """
    Unified form for:
    - Assigning tools to users
    - Transferring tools between users
    - Dispatching tools/materials to projects
    """
    transfer_type = forms.ChoiceField(
        choices=[
            ('assign', 'Assign Tool to User'),
            ('dispatch', 'Dispatch to Project')
        ],
        widget=forms.RadioSelect(attrs={'class': 'transfer-type-radio'}),
        initial='assign',
        label="Action Type"
    )

    # For tool assignments/transfers
    assignment = forms.ModelChoiceField(
        queryset=Assignment.objects.filter(return_date__isnull=True),
        label="Transfer Tool From (current assignment)",
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        help_text="Select to transfer tool to another user"
    )

    available_item = forms.ModelChoiceField(
        queryset=Item.objects.filter(status='AVAILABLE'),
        label="Select Available Item",
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        help_text="Select available tool or material"
    )

    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        label="Assign To User",
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        help_text="Only for tool assignments"
    )

    # For dispatches
    project = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Project name'
        }),
        label="Project Name"
    )

    site_location = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Site location'
        }),
        label="Site Location"
    )

    quantity = forms.IntegerField(
        required=False,
        initial=1,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '1'
        }),
        label="Quantity",
        help_text="For materials only - how many units to dispatch"
    )

    # Common fields
    transfer_date = forms.DateField(
        initial=date.today,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Date"
    )
    expected_return_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text="Only for tools - materials won't return"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Notes...'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Format assignment display
        self.fields['assignment'].label_from_instance = lambda assignment: (
            f"{assignment.item.name} ({assignment.item.serial_number}) - "
            f"Currently with {assignment.assigned_to.get_full_name() or assignment.assigned_to.username}"
        )

        # Format available item display
        self.fields['available_item'].label_from_instance = lambda item: (
            f"{item.name} ({item.serial_number}) - {item.get_item_type_display()}"
        )

        # Format user display
        self.fields['assigned_to'].label_from_instance = lambda user: (
            f"{user.get_full_name()} ({user.username})"
            if user.get_full_name()
            else user.username
        )

        # Set default expected return date (7 days from now)
        if not self.initial.get('expected_return_date'):
            self.initial['expected_return_date'] = (date.today() + timedelta(days=7)).isoformat()

    def clean(self):
        cleaned_data = super().clean()
        transfer_type = cleaned_data.get('transfer_type')
        assignment = cleaned_data.get('assignment')
        available_item = cleaned_data.get('available_item')
        assigned_to = cleaned_data.get('assigned_to')
        project = cleaned_data.get('project')
        quantity = cleaned_data.get('quantity') or 1
        transfer_date = cleaned_data.get('transfer_date')
        expected_return_date = cleaned_data.get('expected_return_date')

        # Validate based on transfer type
        if transfer_type == 'assign':
            # Must select either an assigned item or available item
            if not assignment and not available_item:
                raise ValidationError('Please select either an assigned tool to transfer or an available item.')

            # Cannot select both
            if assignment and available_item:
                raise ValidationError('Please select either an assigned tool OR an available item, not both.')

            # Can only assign TOOLS to users
            item = assignment.item if assignment else available_item
            if item and item.item_type != 'TOOL':
                raise ValidationError('You can only assign TOOLS to users. Materials must be dispatched to projects.')

            # Must have a user to assign to
            if not assigned_to:
                raise ValidationError({'assigned_to': 'Please select a user to assign the tool to.'})

            # Cannot transfer to same user
            if assignment and assigned_to and assignment.assigned_to == assigned_to:
                raise ValidationError("Cannot transfer to the same user who currently has the tool.")

        elif transfer_type == 'dispatch':
            # Get the item
            item = available_item or (assignment.item if assignment else None)
            if not item:
                raise ValidationError('Please select an item to dispatch.')
            if not project:
                raise ValidationError({'project': 'Please enter a project name for dispatch.'})

            # For materials, check quantity
            if item.item_type == 'MATERIAL':
                if quantity > item.quantity:
                    raise ValidationError(f'Cannot dispatch {quantity} units. Only {item.quantity} available.')

        # Date validation
        if transfer_date and expected_return_date:
            if expected_return_date < transfer_date:
                self.add_error('expected_return_date', 'Return date cannot be before action date')

        return cleaned_data
