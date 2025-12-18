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

    # Link to tracker Pace (especially for team leads)
    # This creates a bridge between the employees app and tracker app
    tracker_pace = models.OneToOneField(
        'tracker.Pace',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee',
        verbose_name="Linked Tracker PACe",
        help_text="Connected PACe from tracker app for team leads"
    )

    # Additional fields for future HR/management features
    email = models.EmailField(blank=True, null=True, help_text="Employee email address")
    phone = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    join_date = models.DateField(null=True, blank=True, help_text="Date of joining")

    class Meta:
        ordering = ['name']
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def __str__(self):
        return f"{self.name} ({self.get_designation_display()})"
