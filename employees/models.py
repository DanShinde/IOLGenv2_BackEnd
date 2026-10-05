# employees/models.py
"""
Unified employee management across all apps.
This app provides a centralized Employee model that can be used by tracker, planner, and future apps.
"""

from django.db import models


class Employee(models.Model):
    """
    Unified employee model for all apps.
    Represents all personnel: Engineers, Team Leads, Managers, etc.
    Can be linked to tracker.Pace for team leads.
    """
    DESIGNATION_CHOICES = [
        ('ENGINEER', 'Engineer'),
        ('TEAM_LEAD', 'Team Lead'),
        ('MANAGER', 'Manager'),
    ]

    name = models.CharField(max_length=100)
    designation = models.CharField(max_length=10, choices=DESIGNATION_CHOICES)
    is_active = models.BooleanField(default=True, verbose_name="Active Status")
    last_working_day = models.DateField(
        null=True, blank=True,
        help_text="Set when the employee is made inactive. From the next day they are not "
                  "counted on site, in office or on leave, and any open site/office "
                  "allocation is relieved on this date.",
    )

    # Additional fields for future HR/management features
    email = models.EmailField(blank=True, null=True, help_text="Employee email address")
    phone = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    join_date = models.DateField(null=True, blank=True, help_text="Date of joining")
    segment = models.ForeignKey('planner.Segment', on_delete=models.SET_NULL, null=True, blank=True, help_text="Segment for Engineer/Team Lead. Managers leave this blank.")

    class Meta:
        ordering = ['name']
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def __str__(self):
        return f"{self.name} ({self.get_designation_display()})"

    def save(self, *args, **kwargs):
        # One rule however the status is changed (Workforce, admin, Skill Gap Analyzer):
        # inactive always has a last working day (today if none was chosen), active has none.
        if self.is_active:
            self.last_working_day = None
        elif self.last_working_day is None:
            from django.utils import timezone
            self.last_working_day = timezone.localdate()
        super().save(*args, **kwargs)
        if not self.is_active:
            self.relieve_allocations()

    def relieve_allocations(self):
        """An inactive employee isn't at any site or office: end every site/office
        allocation still running after the last working day on that day."""
        from django.db.models import Q
        from planner.models import SiteAllocation
        lwd = self.last_working_day
        (SiteAllocation.objects
            .filter(employee=self, start_date__lte=lwd)
            .filter(Q(end_date__isnull=True) | Q(end_date__gt=lwd))
            .update(end_date=lwd))
