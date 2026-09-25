from django.db import models
from django.contrib.auth.models import User
from django.db.models import F, Sum
from employees.models import Employee
from .utils import OTIF_EXCLUDED_STAGES
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
    is_archived = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)
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
        # Dispatch and Handover never count toward OTIF (see utils.OTIF_EXCLUDED_STAGES).
        completed_stages = self.stages.filter(status='Completed').exclude(name__in=OTIF_EXCLUDED_STAGES)
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

    def _stages_in_phase_order(self, stage_type=None):
        """This project's stages in phase order (project-level Handover last), then stage
        list order. Reads self.stages.all() and self.phases.all() so a caller that
        prefetched them (the project list page does) costs no extra queries; phase numbers
        come from the phases rather than stage.phase for the same reason."""
        phase_numbers = {p.id: p.number for p in self.phases.all()}
        stages = [s for s in self.stages.all() if stage_type is None or s.stage_type == stage_type]
        stages.sort(key=lambda s: (phase_numbers.get(s.phase_id, 10**6), s.id))
        return stages

    def get_current_automation_stage(self):
        stages = self._stages_in_phase_order('Automation')
        for stage in stages:
            if stage.status not in ['Completed', 'Not Applicable']:
                return stage.name
        return "Completed" if stages else "N/A"

    def get_current_emulation_stage(self):
        stages = self._stages_in_phase_order('Emulation')
        for stage in stages:
            if stage.status not in ['Completed', 'Not Applicable']:
                return stage.name
        return "Completed" if stages else "N/A"

    def _create_phase_stages(self, phase):
        """One phase's worth of stages: every stage except Handover, which is a single
        project-level stage (phase=None) rather than repeated per phase."""
        for stage_name, _ in Stage.AUTOMATION_STAGES:
            if stage_name != Stage.HANDOVER:
                Stage.objects.create(project=self, phase=phase, name=stage_name, stage_type='Automation')
        for stage_name, _ in Stage.EMULATION_STAGES:
            Stage.objects.create(project=self, phase=phase, name=stage_name, stage_type='Emulation')

    def seed_stages(self):
        """Stage checklist for a brand-new project: Phase 1 plus the one Handover stage."""
        phase = Phase.objects.create(project=self, number=1)
        self._create_phase_stages(phase)
        Stage.objects.create(project=self, phase=None, name=Stage.HANDOVER, stage_type='Automation')
        return phase

    def add_phase(self, zone_description=''):
        """Appends the next phase, with a fresh (blank-dated) copy of the stage list."""
        last = self.phases.order_by('-number').first()
        phase = Phase.objects.create(project=self, number=(last.number + 1) if last else 1,
                                     zone_description=zone_description)
        self._create_phase_stages(phase)
        return phase


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
        all_stages = self._stages_in_phase_order()
        completed = [s for s in all_stages if s.status == 'Completed']

        if completed:
            last_done = completed[-1]
            next_index = all_stages.index(last_done) + 1
            if next_index < len(all_stages):
                return all_stages[next_index]
        else:
            return all_stages[0] if all_stages else None

# tracker/models.py

class Phase(models.Model):
    """A delivery phase of a project. Each phase carries its own copy of the stage list
    (except Handover, which is one project-level stage). Start/finish dates and progress
    are derived from the phase's stages at render time, never stored."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='phases')
    number = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=100, blank=True)
    zone_description = models.TextField(blank=True, help_text="Which zone/scope of the project this phase covers.")

    class Meta:
        ordering = ['number']
        unique_together = ('project', 'number')

    @property
    def label(self):
        return self.name or f"Phase {self.number}"

    def __str__(self):
        return f"{self.project.code} - {self.label}"


class Stage(models.Model):
    HANDOVER = "Handover"

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
    # Null only for the project-level Handover stage.
    phase = models.ForeignKey(Phase, on_delete=models.CASCADE, null=True, blank=True, related_name='stages')
    name = models.CharField(max_length=100, choices=STAGE_NAMES)
    stage_type = models.CharField(max_length=20, choices=STAGE_TYPE_CHOICES, default='Automation')
    planned_start_date = models.DateField(null=True, blank=True)
    planned_date = models.DateField(null=True, blank=True)
    actual_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="Not started")
    completion_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    def save(self, *args, **kwargs):
        # Keep the phase rules true however a stage is saved (admin, Excel import, shell):
        # Handover is the single project-level stage (no phase), and every other stage
        # belongs to a phase -- a stage arriving without one joins the project's first.
        if self.name == self.HANDOVER:
            self.phase = None
        elif self.phase_id is None and self.project_id:
            self.phase = (
                self.project.phases.order_by('number').first()
                or Phase.objects.create(project=self.project, number=1)
            )
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'phase' not in update_fields:
            kwargs['update_fields'] = list(update_fields) + ['phase']
        super().save(*args, **kwargs)

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

class DelayReasonTag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class StageDelayReason(models.Model):
    stage = models.OneToOneField(Stage, on_delete=models.CASCADE, related_name='delay_reason')
    reasons = models.ManyToManyField(DelayReasonTag, related_name='stage_delays', blank=True)
    description = models.TextField(blank=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Delay reason for {self.stage}"

# General project-level comments/chat
class ProjectComment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='comments')
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Comment by {self.added_by} on {self.project.code} at {self.created_at}"


# ✅ NEW MODEL: ContactPerson
class ContactPerson(models.Model):
    first_name = models.CharField(max_length=50, null=True) # Required in Admin
    last_name = models.CharField(max_length=50, null=True)  # Required in Admin
    name = models.CharField(max_length=100, unique=True, blank=True) # Auto-populated
    email = models.EmailField(max_length=254, blank=True, null=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # 1. If First/Last provided, update Name
        if self.first_name and self.last_name:
            self.name = f"{self.first_name} {self.last_name}"
        
        # 2. If Name provided but First/Last missing (e.g. from Quick Add), split Name
        elif self.name:
            parts = self.name.strip().split(' ', 1)
            if not self.first_name:
                self.first_name = parts[0]
            if not self.last_name:
                self.last_name = parts[1] if len(parts) > 1 else ""
            # Ensure name is consistent
            self.name = f"{self.first_name} {self.last_name}".strip()

        # 3. Auto-generate Email if missing
        if not self.email and self.first_name and self.last_name:
            clean_first = self.first_name.strip().replace(' ', '')
            clean_last = self.last_name.strip().replace(' ', '')
            self.email = f"{clean_first}.{clean_last}@armstrongdematic.com".lower()

        super().save(*args, **kwargs)

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
        ('Archived', 'Archived'),
    ]

    PUSH_PULL_CHOICES = [
        ('Pull', 'Pull Content'),
        ('Push', 'Push Content'),
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
    push_pull_type = models.CharField(max_length=10, choices=PUSH_PULL_CHOICES, default='Pull')
    who_contact = models.ManyToManyField(ContactPerson, blank=True, related_name='updates_assigned_to')
    raised_by = models.ForeignKey(ContactPerson, on_delete=models.SET_NULL, null=True, blank=True, related_name='updates_raised_by')
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


class SavedReportFilter(models.Model):
    """A user's named, bookmarked filter combination for the Project Reports page."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_report_filters')
    name = models.CharField(max_length=100)
    query_string = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('user', 'name')

    def __str__(self):
        return f"{self.user} - {self.name}"

    def __str__(self):
        return f"Remark on Update {self.update.id} by {self.added_by.username} at {self.created_at}"