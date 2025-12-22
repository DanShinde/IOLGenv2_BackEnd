# planner/models.py

from django.db import models
from django.utils import timezone
from datetime import timedelta
from .utils import calculate_end_date
from employees.models import Employee

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
    customer_name = models.CharField(max_length=200)
    segment = models.ForeignKey(Segment, on_delete=models.SET_NULL, null=True, blank=True)
    team_lead = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'designation': 'TEAM_LEAD'},
        related_name='led_projects',
        verbose_name="Team Lead"
    )
    # Link to tracker project - won't delete planner project if tracker project is deleted
    tracker_project = models.OneToOneField(
        'tracker.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planner_project',
        verbose_name="Linked Tracker Project",
        help_text="Connected project from tracker app"
    )

    class Meta:
        ordering = ['project_id']
    def __str__(self):
        return self.project_id

class Activity(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    activity_name = models.CharField(max_length=200)
    project_type = models.ForeignKey(ProjectType, on_delete=models.SET_NULL, null=True, blank=True)
    assignee = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True, blank=True)
    remark = models.TextField(blank=True)
    start_date = models.DateField(default=timezone.now)
    duration = models.PositiveIntegerField(default=1, help_text="Duration in working days")
    end_date = models.DateField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.project.project_id} - {self.activity_name}"
        
    def save(self, *args, **kwargs):
        # 1. Get Global Holidays
        holidays = list(Holiday.objects.values_list('date', flat=True))
        
        # 2. Get Assignee Leaves (if assigned)
        assignee_leaves = []
        if self.assignee:
            # We only care about leaves that happen on or after the activity start
            relevant_leaves = self.assignee.leaves.filter(end_date__gte=self.start_date)
            for leave in relevant_leaves:
                # Expand range to individual dates
                curr = leave.start_date
                while curr <= leave.end_date:
                    assignee_leaves.append(curr)
                    curr += timedelta(days=1)
        
        # 3. Calculate End Date considering both
        self.end_date = calculate_end_date(self.start_date, self.duration, holidays, assignee_leaves)
        super().save(*args, **kwargs)
        
    class Meta:
        ordering = ['start_date']

class Leave(models.Model):
    employee = models.ForeignKey('employees.Employee', on_delete=models.CASCADE, related_name='planner_leaves')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.employee.name} ({self.start_date} to {self.end_date})"
    
    class Meta:
        ordering = ['-start_date']

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