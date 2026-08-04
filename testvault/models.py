from django.contrib.auth.models import User
from django.db import models


class TestVaultProject(models.Model):
    """A FAT/SAT test case run for a project. Deliberately holds no project identity of its
    own (no code/customer_name fields) -- that lives on tracker.Project, the single source of
    truth shared with Tracker/Planner. Created either by picking a tracker.Project directly, or
    by picking a planner.Project and resolving its linked tracker_project."""

    VALIDATOR_TYPE_CHOICES = [
        ('Self', 'Self'),
        ('Internal Validator', 'Internal Validator'),
        ('External Validator', 'External Validator'),
    ]
    TESTING_PHASE_CHOICES = [
        ('Emulation', 'Emulation'),
        ('FAT', 'FAT'),
        ('SAT', 'SAT'),
    ]

    tracker_project = models.ForeignKey(
        'tracker.Project', on_delete=models.CASCADE, related_name='testvault_projects'
    )
    zone_name = models.CharField(max_length=200, blank=True)
    prepared_by = models.ForeignKey(
        'employees.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='testvault_prepared_projects', verbose_name="Test Cases Prepared By"
    )
    # Free text, not a real date -- the source app's UI defaults it to today's date formatted
    # DD-MM-YYYY but never parses it; it's just display/report text a user can edit freely.
    date_of_validation = models.CharField(max_length=20, blank=True)
    validator_type = models.CharField(max_length=20, choices=VALIDATOR_TYPE_CHOICES, default='Self')
    validator_employee = models.ForeignKey(
        'employees.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='testvault_validated_projects',
        help_text="Used when Validator Type is Internal Validator"
    )
    validator_name = models.CharField(
        max_length=150, blank=True,
        help_text="Free-text validator name, used when Validator Type is External Validator"
    )
    testing_phase = models.CharField(max_length=20, choices=TESTING_PHASE_CHOICES, default='Emulation')

    sections = models.JSONField(default=list, blank=True)
    custom_selection_types = models.JSONField(default=list, blank=True)
    deleted_selection_types = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "TestVault Project"

    def __str__(self):
        label = self.zone_name or "Test Vault"
        return f"{self.tracker_project.code} — {label}"

    @property
    def project_code(self):
        return self.tracker_project.code

    @property
    def customer_name(self):
        return self.tracker_project.customer_name

    def to_engine_dict(self):
        """Shape matching the ported engine's Project.to_dict(), for handing off to
        TestCaseEngine/WorkbookBuilder or returning as the SPA's project state payload."""
        return {
            "info": {
                "project_code": self.project_code,
                "zone_name": self.zone_name,
                "customer_name": self.customer_name,
                "done_by": self.prepared_by.name if self.prepared_by else "",
                "date_of_validation": self.date_of_validation,
                "validator_type": self.validator_type,
                "validator_name": self.validator_employee.name if self.validator_employee else self.validator_name,
                "testing_phase": self.testing_phase,
            },
            "sections": self.sections,
            "custom_selection_types": self.custom_selection_types,
            "deleted_selection_types": self.deleted_selection_types,
        }


class ReportSession(models.Model):
    """Persisted view-only share snapshot for the 'Share Report' link. Replaces the source
    app's module-level dict (Web/server.py _report_sessions), which only survives in a single
    process -- this Django project typically runs multiple gunicorn workers."""

    id = models.CharField(max_length=8, primary_key=True)
    project_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.id
