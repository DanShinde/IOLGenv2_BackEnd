# planner/models.py

from django.db import models
from django.utils import timezone
from .utils import calculate_end_date

class Segment(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "Categories"

class ProjectType(models.Model):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    engineer_involvement = models.FloatField(default=100.0)
    team_lead_involvement = models.FloatField(default=30.0)
    manager_involvement = models.FloatField(default=5.0)
    class Meta:
        unique_together = ('segment', 'category')
    def __str__(self): 
        return f"{self.segment.name} - {self.category.name}"

class Project(models.Model):
    project_id = models.CharField(max_length=100, unique=True, verbose_name="Project Code")
    # --- REMOVED ---
    # name = models.CharField(max_length=200, blank=True, verbose_name="Project Name")
    customer_name = models.CharField(max_length=200)
    segment = models.ForeignKey(Segment, on_delete=models.SET_NULL, null=True, blank=True)
    team_lead = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'designation': 'TEAM_LEAD'},
        related_name='led_projects',
        verbose_name="Team Lead"
    )

    class Meta:
        ordering = ['project_id']
    def __str__(self):
        return self.project_id

class Activity(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    activity_name = models.CharField(max_length=200)
    project_type = models.ForeignKey(ProjectType, on_delete=models.SET_NULL, null=True, blank=True)
    assignee = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True)
    remark = models.TextField(blank=True)
    start_date = models.DateField(default=timezone.now)
    duration = models.PositiveIntegerField(default=1, help_text="Duration in working days")
    end_date = models.DateField(blank=True, null=True)
    def __str__(self):
        return f"{self.project.project_id} - {self.activity_name}"
    def save(self, *args, **kwargs):
        holidays = list(Holiday.objects.values_list('date', flat=True))
        self.end_date = calculate_end_date(self.start_date, self.duration, holidays)
        super().save(*args, **kwargs)
    class Meta:
        ordering = ['start_date']

class Employee(models.Model):
    DESIGNATION_CHOICES = [
        ('ENGINEER', 'Engineer'),
        ('TEAM_LEAD', 'Team Lead'),
        ('MANAGER', 'Manager'),
    ]
    name = models.CharField(max_length=100)
    designation = models.CharField(max_length=10, choices=DESIGNATION_CHOICES)
    def __str__(self): return self.name
    class Meta: ordering = ['name']

class Holiday(models.Model):
    date = models.DateField(unique=True)
    description = models.CharField(max_length=200)
    def __str__(self): return f"{self.date.strftime('%Y-%m-%d')} - {self.description}"
    class Meta: ordering = ['date']

class GeneralSettings(models.Model):
    working_hours_per_day = models.FloatField(default=8.0)
    def __str__(self):
        return "General Settings"
    class Meta:
        verbose_name_plural = "General Settings"

class CapacitySettings(models.Model):
    designation = models.CharField(max_length=10, choices=Employee.DESIGNATION_CHOICES, unique=True)
    monthly_meeting_hours = models.FloatField(default=0)
    monthly_leave_hours = models.FloatField(default=0)
    efficiency_loss_factor = models.FloatField(default=0.0, help_text="Percentage, e.g., 10 for 10%")
    def __str__(self):
        return f"Capacity Settings for {self.get_designation_display()}s"
    class Meta:
        verbose_name_plural = "Capacity Settings"

class SalesForecast(models.Model):
    opportunity = models.CharField(max_length=100, unique=True)
    total_amount = models.FloatField(default=0)
    probability = models.FloatField(default=0, help_text="Percentage, e.g., 90 for 90%")
    segment = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=100, blank=True)
    solution = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    def __str__(self):
        return self.opportunity
    class Meta:
        ordering = ['opportunity']

class EffortBracket(models.Model):
    project_type = models.ForeignKey(ProjectType, on_delete=models.CASCADE, related_name='effort_brackets')
    project_value = models.FloatField(help_text="The monetary value of the project.")
    effort_days = models.PositiveIntegerField(help_text="The standard number of working days for this value.")

    def __str__(self):
        return f"{self.project_type}: {self.project_value:,.0f} = {self.effort_days} Days"

    class Meta:
        ordering = ['project_value']
        unique_together = ('project_type', 'project_value')