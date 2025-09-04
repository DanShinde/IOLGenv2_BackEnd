from django.db import models
from django.contrib.auth.models import User
from django.db.models import F


# Define the Segment model
class trackerSegment(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
class Pace(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "PACe"
        verbose_name_plural = "PACe"

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
    pace = models.ForeignKey(
        Pace,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects"
    )

    def __str__(self):
        return self.code

    def get_completion_percentage(self):
        stages = self.stages.exclude(status="Not Applicable")
        total = stages.count()
        completed = stages.filter(status="Completed").count()
        return round((completed / total) * 100) if total > 0 else 0

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
    planned_date = models.DateField(null=True, blank=True)
    actual_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="Not started")

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


class ProjectUpdate(models.Model):
    CATEGORY_CHOICES = [
        ('Information', 'Information'),
        ('Action', 'Action'),
        ('Risk', 'Risk'),
    ]
    
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='updates')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Information')
    needs_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # ✅ NEW FIELDS
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Open', null=True, blank=True)
    mitigation_plan = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Update for {self.project.code} at {self.created_at.strftime('%Y-%m-%d')}"