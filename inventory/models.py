from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone


# Condition of a TOOL at the moment it's returned from an assignment or dispatch
RETURN_CONDITION_CHOICES = [
    ('GOOD', 'Good - No Issues'),
    ('DAMAGED', 'Damaged'),
    ('NEEDS_REPAIR', 'Needs Repair'),
    ('LOST', 'Lost / Not Returned'),
]


def resolve_return_status(condition):
    """
    Map the condition a tool is returned in to where it ends up.
    Returns (item_status, location, history_action).
    """
    if condition == 'LOST':
        return 'RETIRED', 'Lost', 'RETIRED'
    if condition in ('DAMAGED', 'NEEDS_REPAIR'):
        return 'MAINTENANCE', 'Warehouse - Maintenance', 'MAINTENANCE'
    return 'AVAILABLE', 'Warehouse', 'RETURNED'


class ProvisionedUser(models.Model):
    """
    Marks a User account inventory itself created (as a login-disabled placeholder
    for an active employee who had no login yet), as opposed to a real account
    that already existed via Planner/skill gap analyzer's own user management.

    This is the definitive signal for "safe to offer deleting from inventory" -
    real employee-managed accounts must never be deletable from here.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='inventory_provisioned')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Provisioned: {self.user.username}"


class Item(models.Model):
    """
    Main Item model - tracks both Tools and Materials
    """
    ITEM_TYPES = [
        ('TOOL', 'Tool'),
        ('MATERIAL', 'Material'),
    ]

    STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('ASSIGNED', 'Assigned'),      # Only for TOOLS
        ('DISPATCHED', 'Dispatched'),  # Only for TOOLS
        ('CONSUMED', 'Consumed'),      # Only for MATERIALS - once dispatched, marked as consumed
        ('MAINTENANCE', 'Under Maintenance'),  # Only for TOOLS - returned damaged/needing repair
        ('RETIRED', 'Retired'),
    ]

    # Basic Information
    item_type = models.CharField(max_length=10, choices=ITEM_TYPES)
    name = models.CharField(max_length=100, db_index=True)
    model = models.CharField(max_length=50, blank=True)
    serial_number = models.CharField(max_length=50, unique=True, db_index=True)
    make = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='item_images/', null=True, blank=True)

    # Purchase Information
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Quantity (mainly for materials)
    quantity = models.PositiveIntegerField(default=1, help_text="For materials: current stock. For tools: always 1")
    min_quantity = models.PositiveIntegerField(default=0, help_text="Alert when stock falls below this")

    # Current Location & Organization
    location = models.CharField(max_length=100, blank=True, db_index=True,
                                help_text="Where is this item right now?")
    category = models.CharField(max_length=50, blank=True, db_index=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE', db_index=True)

    # Remarks - for any updates or notes
    remarks = models.TextField(blank=True, help_text="General notes, updates, or any important information")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_items')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['item_type', 'status']),
            models.Index(fields=['category', 'status']),
        ]

    def __str__(self):
        return f"{self.name} ({self.serial_number})"

    def get_absolute_url(self):
        return reverse('inventory-item-detail', kwargs={'pk': self.pk})

    @property
    def needs_reorder(self):
        """Check if material stock is below minimum threshold"""
        if self.item_type == 'MATERIAL':
            return self.quantity <= self.min_quantity
        return False

    @property
    def current_location_display(self):
        """Get human-readable current location"""
        if self.status == 'AVAILABLE':
            return f"Warehouse - {self.location}" if self.location else "Warehouse"
        elif self.status == 'ASSIGNED':
            # Get current assignment
            assignment = self.assignments.filter(return_date__isnull=True).first()
            if assignment:
                return f"Assigned to {assignment.assigned_to.get_full_name() or assignment.assigned_to.username}"
        elif self.status == 'DISPATCHED':
            # Get current dispatch
            dispatch = self.dispatches.filter(return_date__isnull=True).first()
            if dispatch:
                who = 'unknown'
                if dispatch.responsible_person:
                    who = dispatch.responsible_person.get_full_name() or dispatch.responsible_person.username
                return f"Dispatched to {dispatch.project} ({dispatch.site_location or 'N/A'}) - with {who}"
        elif self.status == 'CONSUMED':
            return "Consumed (No longer in inventory)"
        elif self.status == 'MAINTENANCE':
            return f"Under Maintenance - {self.location}" if self.location else "Under Maintenance"
        elif self.status == 'RETIRED':
            return "Retired"
        return self.location or "Unknown"


class Assignment(models.Model):
    """
    Track tool assignments to users
    Tools can be assigned to users and returned
    """
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='assignments',
                             limit_choices_to={'item_type': 'TOOL'})
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tool_assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assigned_items')
    assignment_date = models.DateField()
    expected_return_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    return_condition = models.CharField(max_length=20, choices=RETURN_CONDITION_CHOICES, blank=True,
                                        help_text="Condition of the tool when it was returned")
    return_notes = models.TextField(blank=True, help_text="Notes recorded at return time (e.g. damage description)")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-assignment_date']

    def __str__(self):
        return f"{self.item.name} assigned to {self.assigned_to.get_full_name() or self.assigned_to.username}"

    def is_active(self):
        """Check if this assignment is currently active"""
        return self.return_date is None

    @property
    def is_overdue(self):
        """Check if assignment is overdue"""
        if self.return_date or not self.expected_return_date:
            return False
        return timezone.now().date() > self.expected_return_date

    @property
    def days_overdue(self):
        """Calculate days overdue"""
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.expected_return_date).days


class Dispatch(models.Model):
    """
    Track dispatches to projects
    - Tools: Can be dispatched and returned
    - Materials: Once dispatched, they are consumed (marked as CONSUMED status)
    """
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='dispatches')
    quantity = models.PositiveIntegerField(default=1, help_text="Quantity dispatched")
    project = models.CharField(max_length=100, db_index=True)
    site_location = models.CharField(max_length=100, null=True, blank=True)
    responsible_person = models.ForeignKey(User, on_delete=models.PROTECT, related_name='responsible_dispatches',
                                           null=True, blank=True,
                                           help_text="Active employee at the site responsible for this item - needed to recover it")
    dispatched_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dispatched_items')
    dispatch_date = models.DateField()
    expected_return_date = models.DateField(null=True, blank=True,
                                           help_text="Only for tools - materials won't return")
    return_date = models.DateField(null=True, blank=True, help_text="Only applicable for tools")
    return_condition = models.CharField(max_length=20, choices=RETURN_CONDITION_CHOICES, blank=True,
                                        help_text="Condition of the tool when it was returned (tools only)")
    return_notes = models.TextField(blank=True, help_text="Notes recorded at return time (e.g. damage description)")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-dispatch_date']
        verbose_name_plural = 'Dispatches'

    def __str__(self):
        who = 'unknown'
        if self.responsible_person:
            who = self.responsible_person.get_full_name() or self.responsible_person.username
        if self.item.item_type == 'TOOL':
            return f"{self.item.name} dispatched to {self.project} (with {who})"
        else:
            return f"{self.quantity} x {self.item.name} dispatched to {self.project} (Consumed, received by {who})"

    def is_active(self):
        """Check if this dispatch is currently active (only for tools)"""
        if self.item.item_type == 'MATERIAL':
            return False  # Materials are immediately consumed
        return self.return_date is None

    @property
    def is_overdue(self):
        """Check if dispatch is overdue (only for tools)"""
        if self.item.item_type == 'MATERIAL':
            return False
        if self.return_date or not self.expected_return_date:
            return False
        return timezone.now().date() > self.expected_return_date

    @property
    def days_overdue(self):
        """Calculate days overdue (only for tools)"""
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.expected_return_date).days


class Reservation(models.Model):
    """
    Book a tool ahead of time for a user over a date range.
    Fulfilling a reservation converts it into a real Assignment.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('FULFILLED', 'Fulfilled'),
        ('CANCELLED', 'Cancelled'),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='reservations',
                             limit_choices_to={'item_type': 'TOOL'})
    reserved_for = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tool_reservations',
                                     help_text="Who the tool is being held for")
    reserved_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_reservations',
                                    help_text="Who made the booking")
    start_date = models.DateField(help_text="When the tool is needed from")
    end_date = models.DateField(help_text="When the tool is expected to be returned")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    notes = models.TextField(blank=True)
    fulfilled_assignment = models.OneToOneField(Assignment, on_delete=models.SET_NULL, null=True, blank=True,
                                                 related_name='source_reservation')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_date']

    def __str__(self):
        return f"{self.item.name} reserved for {self.reserved_for.get_full_name() or self.reserved_for.username} ({self.start_date} to {self.end_date})"

    @property
    def is_expired(self):
        """A pending reservation whose window has passed without being fulfilled"""
        return self.status == 'PENDING' and self.end_date < timezone.now().date()

    def overlaps(self, start_date, end_date):
        return self.start_date <= end_date and self.end_date >= start_date


class History(models.Model):
    """
    Complete audit trail - tracks WHERE items have been
    Every movement, assignment, dispatch, return is logged here
    """
    ACTION_CHOICES = [
        ('ADDED', 'Added to Inventory'),
        ('UPDATED', 'Information Updated'),
        ('RESERVED', 'Reserved for User'),
        ('ASSIGNED', 'Assigned to User'),
        ('RETURNED', 'Returned to Warehouse'),
        ('TRANSFERRED', 'Transferred to Another User'),
        ('DISPATCHED', 'Dispatched to Project'),
        ('CONSUMED', 'Material Consumed'),
        ('MAINTENANCE', 'Sent to Maintenance'),
        ('RETIRED', 'Retired from Service'),
        ('LOCATION_CHANGED', 'Location Changed'),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='history')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                            help_text="User who performed this action")
    details = models.TextField(blank=True, help_text="Detailed information about this action")
    location = models.CharField(max_length=200, blank=True, help_text="Location at time of action")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Histories'
        indexes = [
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.item.name} - {self.get_action_display()} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
