from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

# Define the Segment model
class Segment(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
# Define the PLC model
class PLC(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
# Define the PLC model
class IODevice(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
# Define the Segment model
class DeviceType(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
# Updated Project model
class Project(models.Model):
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=500, blank=True)
    segments = models.ManyToManyField(Segment, blank=True)  # Many-to-Many for segments
    PLC = models.ForeignKey(PLC, on_delete=models.SET_NULL, null=True, blank=True)  # Single selection with dynamic options
    created_by = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField()
    io_device = models.CharField(max_length=30, blank=True, null=True)
    isFreeze = models.BooleanField(default=False)
    panels = models.JSONField(blank=True, null=True)
    panel_numbers = models.CharField(max_length=1000, blank=True, null=True)
    exported_at = models.DateTimeField(blank=True, null=True)
    exported_by = models.CharField(max_length=30, blank=True, null=True)

    def __str__(self):
        return self.name


class ProjectReport(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField()
    created_by = models.CharField(max_length=50, blank=True, null=True)
    segment = models.CharField(blank=True)  # Updated to handle multiple segments
    PLC = models.CharField(max_length=50, blank=True)  # Store the PLC name as a string

    def __str__(self):
        return str(self.project)


@receiver(post_save, sender=Project)
def create_project_report(sender, instance, created, **kwargs):
    if created:
        ProjectReport.objects.create(
            project=instance,
            created_at=instance.created_at,
            created_by=instance.created_by,
            segment=", ".join([segment.name for segment in instance.segments.all()]),
            PLC=instance.PLC.name if instance.PLC else "",
        )



class Module(models.Model):
    id = models.IntegerField(primary_key=True)
    module = models.CharField(max_length=50)
    description = models.CharField(max_length=500, blank=True)
    created_by = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    segment = models.ForeignKey(Segment, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self):
        return self.module

class IOList(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    name = models.CharField(max_length=30)
    equipment_code = models.CharField(max_length=30)
    code = models.CharField(max_length=40)
    tag = models.CharField(max_length=100, editable=True)
    signal_type = models.CharField(max_length=10)
    device_type = models.CharField(max_length=100, blank=True)
    actual_description = models.CharField(max_length=200)
    panel_number = models.CharField(max_length=10, blank=True, null=True, default='CP01') #models.CharField(max_length=30, choices=[(k, k) for k in project.panel_keys]) 
    module_position = models.IntegerField(blank=True, null=True)
    channel = models.IntegerField( blank=True, null=True)
    location = models.CharField(max_length=2, choices=(('FD', 'FD'), ('CP', 'CP')), default='CP')
    io_address = models.CharField(max_length=20, blank=True, null=True)
    Cluster = models.CharField(max_length=50, default="Testing")
    created_by = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    order = models.PositiveIntegerField(null=True)
    cluster_number = models.PositiveIntegerField(null=True)
    iomodule_name = models.CharField(max_length=10, blank=True, null=True)
    Demo_3d_Property = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return self.tag
    
    class Meta:
        ordering = ['order']

class Signal(models.Model):
    id = models.AutoField(primary_key=True)
    equipment_code = models.CharField(max_length=30)
    code = models.CharField(max_length=40)
    function_purpose = models.CharField(max_length=100, blank=True)
    device_type = models.ForeignKey(
        DeviceType, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
    )
    device_type_name = models.CharField(max_length=50, blank=True, null=True)
    signal_type = models.CharField(max_length=10, default="DI", choices=(('DI', 'DI'), ('DO', 'DO'), ('Encoder', 'Encoder')))
    remarks = models.CharField(max_length=100, blank=True)
    segment = models.CharField(max_length=100, blank=True, editable=False)  # segment as text field, not a foreign key
    initial_state = models.BooleanField(default=True)
    location = models.CharField(max_length=2, choices=(('FD', 'FD'), ('CP', 'CP')))
    module = models.ForeignKey(Module, on_delete=models.CASCADE, default=1, related_name="modules")
    created_by = models.CharField(max_length=30)
    updated_by = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    Demo_3d_Property = models.CharField(max_length=200, blank=True, null=True)

    def save(self, *args, **kwargs):
        # Set the segment field based on the module's segment
        if self.module:
            self.segment = self.module.segment.name

        # Set 'created_by' and 'updated_by' based on the current user if available
        user = kwargs.get('user', None)  # Pass the current user when saving
        if user:
            user_full_name = f"{user.first_name} {user.last_name}"
            if not self.created_by:
                self.created_by = user_full_name
            self.updated_by = user_full_name

        # Store the name of the DeviceType before saving
        if self.device_type:
            self.device_type_name = self.device_type.name
        super(Signal, self).save(*args, **kwargs)

    def __str__(self):
        if self.equipment_code != '':
            return f'{self.equipment_code}_{self.code}'
        else:
            return self.code




