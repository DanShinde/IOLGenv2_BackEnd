from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

class Item(models.Model):
    ITEM_TYPES = [
        ('TOOL', 'Tool'),
        ('MATERIAL', 'Material'),
    ]
    
    STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('ASSIGNED', 'Assigned'),
        ('DISPATCHED', 'Dispatched'),
        ('RETIRED', 'Retired'),
    ]
    
    item_type = models.CharField(max_length=10, choices=ITEM_TYPES)
    name = models.CharField(max_length=100)
    model = models.CharField(max_length=50, blank=True)
    serial_number = models.CharField(max_length=50, unique=True)
    make = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='item_images/', null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    min_quantity = models.PositiveIntegerField(default=0)
    location = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.serial_number})"
    
    def get_absolute_url(self):
        return reverse('item-detail', kwargs={'pk': self.pk})
    
    @property
    def needs_reorder(self):
        return self.quantity <= self.min_quantity

class Assignment(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assigned_items')
    assignment_date = models.DateField()
    expected_return_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.item.name} assigned to {self.assigned_to.get_full_name() or self.assigned_to.username}"
    
    def is_active(self):
        return self.return_date is None

class Dispatch(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    project = models.CharField(max_length=100)
    site_location = models.CharField(max_length=100, null=True, blank=True)
    dispatched_by = models.ForeignKey(User, on_delete=models.CASCADE)
    dispatch_date = models.DateField()
    expected_return_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        if self.item.item_type == 'TOOL':
            return f"{self.item.name} dispatched to {self.project}"
        else:
            return f"{self.quantity} of {self.item.name} dispatched to {self.project}"
    
    def is_active(self):
        return self.return_date is None

class History(models.Model):
    ACTION_CHOICES = [
        ('ADDED', 'Added'),
        ('UPDATED', 'Updated'),
        ('ASSIGNED', 'Assigned'),
        ('RETURNED', 'Returned'),
        ('TRANSFERRED', 'Transferred'),
        ('DISPATCHED', 'Dispatched'),
        ('MAINTAINED', 'Maintained'),
        ('RETIRED', 'Retired'),
    ]
    
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Histories'
    
    def __str__(self):
        return f"{self.item.name} - {self.get_action_display()}"