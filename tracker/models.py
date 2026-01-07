from django.db import models
from django.contrib.auth.models import User
from django.db.models import F, Sum
from employees.models import Employee
from django.core.validators import MinValueValidator, MaxValueValidator


# Define the Segment model
class trackerSegment(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
class Project(models.Model):
    code = models.CharField(max_length=50, unique=True)
    customer_name = models.CharField(max_length=100)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    so_punch_date = models.DateField()
    # The redundant 'segment' CharField and the custom 'save' method have been removed.
    # 'segment_con' is now the single source of truth.
    segment_con = models.ForeignKey(
        trackerSegment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tracker_projects1"
    )
    team_lead = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'designation': 'TEAM_LEAD'},
        related_name='tracker_projects',
        verbose_name="Team Lead (PACe)"
    )


    def __str__(self):
        return self.code

    def get_completion_percentage(self):
        stages = self.stages.exclude(status="Not Applicable")
        total = stages.count()
        if total > 0:
            total_progress = stages.aggregate(total=Sum('completion_percentage'))['total'] or 0
            return round(total_progress / total)
        return 0

    from datetime import timedelta

    def get_otif_percentage(self):
        completed_stages = self.stages.filter(status='Completed')
        if not completed_stages.exists():
            return None
        on_time = completed_stages.filter(actual_date__lte=F('planned_date')).count()
        total = completed_stages.count()
        return round((on_time / total) * 100, 1)

    def get_overall_status(self):
        stages = self.stages.all()

        if stages.filter(status='Hold').exists():
            return 'Hold'
        elif stages.filter(name='Handover', status='Completed').exists():
            return 'Completed'
        elif stages.exclude(status='Not started').exclude(status='Hold').exists():
            return 'In Progress'
        elif stages.filter(status='Not started').count() == stages.count():
            return 'Not started'
        else:
            return 'Not started'  # fallback


    @property
    def get_schedule_status(self):
        completed = self.stages.filter(status='Completed').order_by('id')
        if not completed.exists():
            return None  # No status possible

        last_stage = completed.last()
        if last_stage.planned_date and last_stage.actual_date:
            delta = (last_stage.actual_date - last_stage.planned_date).days
            return delta  # +ve → delayed, -ve → ahead
        return None

    @property
    def next_milestone(self):
        completed = list(self.stages.filter(status='Completed').order_by('id'))
        all_stages = list(self.stages.all().order_by('id'))

        if completed:
            last_done = completed[-1]
            next_index = all_stages.index(last_done) + 1
            if next_index < len(all_stages):
                return all_stages[next_index]
        else:
            return all_stages[0] if all_stages else None

# tracker/models.py

class Stage(models.Model):
    AUTOMATION_STAGES = [
        ("DAP", "DAP"),
        ("IO List & BOM Release", "IO List & BOM Release"),
        ("Offline Development", "Offline Development"),
        ("Emulation Testing", "Emulation Testing"),
        ("Dispatch", "Dispatch"),
        ("Go Live", "Go Live"),
        ("Handover", "Handover"),
    ]

    EMULATION_STAGES = [
        ("Emulation layout design", "Emulation layout design"),
        ("IO Configuration", "IO Configuration"),
        ("HMI/ SCADA Design", "HMI/ SCADA Design"),
        ("HMI/ SCADA Tagging", "HMI/ SCADA Tagging"),
        ("Audit Of Emulation Layout", "Audit Of Emulation Layout"),
        ("Audit Of HMI/SCADA", "Audit Of HMI/SCADA"),
    ]
    
    # Combine all stage names for the database choices
    STAGE_NAMES = AUTOMATION_STAGES + EMULATION_STAGES

    STATUS_CHOICES = [
        ("Not started", "Not started"),
        ("In Progress", "In Progress"),
        ("Completed", "Completed"),
        ("Hold", "Hold"),
        ("Not Applicable", "Not Applicable"),
    ]
    
    STAGE_TYPE_CHOICES = [
        ("Automation", "Automation"),
        ("Emulation", "Emulation"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='stages')
    name = models.CharField(max_length=100, choices=STAGE_NAMES)
    stage_type = models.CharField(max_length=20, choices=STAGE_TYPE_CHOICES, default='Automation')
    planned_start_date = models.DateField(null=True, blank=True)
    planned_date = models.DateField(null=True, blank=True)
    actual_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="Not started")
    completion_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    def __str__(self):
        return f"{self.project.code} - {self.name}"

class StageHistory(models.Model):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=50)
    old_value = models.CharField(max_length=100, blank=True, null=True)
    new_value = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.stage} | {self.field_name} changed at {self.changed_at}"

class StageRemark(models.Model):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="remarks")
    text = models.TextField()
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Remark for {self.stage.name} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"

# ✅ NEW MODEL: ContactPerson
class ContactPerson(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class ProjectUpdate(models.Model):
    CATEGORY_CHOICES = [
        ('Information', 'Information'),
        ('Action', 'Action'),
        ('Risk', 'Risk'),
    ]
    
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('In Progress', 'In Progress'),
        ('Closed', 'Closed'),
    ]

    PUSH_PULL_CHOICES = [
        ('Push', 'Push Content'),
        ('Pull', 'Pull Content'),
    ]


    # ✅ NEW: Choices for the new content type field
    CONTENT_TYPE_CHOICES = [
        ('Project', 'Project'),
        ('General', 'General'),
    ]

    # ✅ UPDATED: The project field is now optional
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='updates', null=True, blank=True)

    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField()
    # The 'category' and 'needs_review' fields have been removed or commented out.
    # To avoid errors, it's safer to keep them until migrations are run correctly.
    # category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Information')
    # needs_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


    # ✅ UPDATED FIELD: Using the new ContactPerson model
    push_pull_type = models.CharField(max_length=10, choices=PUSH_PULL_CHOICES, default='Push')
    who_contact = models.ManyToManyField(ContactPerson, blank=True, related_name='updates_assigned_to')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    eta = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # ✅ NEW FIELD: To distinguish between project and general content
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPE_CHOICES, default='Project')


    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Update for {self.project.code if self.project else 'General'} at {self.created_at.strftime('%Y-%m-%d')}"


class UpdateRemark(models.Model):
    update = models.ForeignKey(ProjectUpdate, on_delete=models.CASCADE, related_name="remarks")
    text = models.TextField()
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Remark on Update {self.update.id} by {self.added_by.username} at {self.created_at}"