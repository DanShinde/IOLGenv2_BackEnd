from collections import defaultdict

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.utils import timezone

# Mandatory skill gaps count double toward aggregate gap scores, so a missed
# must-have skill moves the number more than a missed nice-to-have.
MANDATORY_GAP_WEIGHT = 2
OPTIONAL_GAP_WEIGHT = 1


def gap_weight(is_mandatory):
    return MANDATORY_GAP_WEIGHT if is_mandatory else OPTIONAL_GAP_WEIGHT


def user_can_manage_employee(user, employee):
    """Staff can manage any employee's ratings; a manager can manage only their own reports."""
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    manager_record = SkillMatrix.objects.filter(user=user).first()
    return bool(manager_record and employee.manager_id == manager_record.id)


class RoleMatrix(models.Model):
    title = models.CharField(max_length=100, help_text="Role/Job Title")
    department = models.CharField(max_length=100, blank=True, null=True, help_text="Department name")
    description = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Role Matrices"
        ordering = ['title']
    
    def __str__(self):
        return self.title
    
    @property
    def name(self):
        return self.title
    
    def get_required_skills(self):
        return self.benchmarks.select_related('skill').all()
    
    def get_benchmark_count(self):
        return self.benchmarks.count()

class Skill(models.Model):
    CATEGORY_CHOICES = [
        ('technical', 'Technical'),
        ('soft', 'Soft Skills'),
        ('leadership', 'Leadership'),
        ('domain', 'Domain Knowledge'),
        ('tools', 'Tools & Software'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name

class SkillBenchmark(models.Model):
    role_matrix = models.ForeignKey(RoleMatrix, on_delete=models.CASCADE, related_name='benchmarks')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='benchmarks')
    required_level = models.IntegerField(
        default=3,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    is_mandatory = models.BooleanField(default=True, help_text="Is this skill mandatory for the role?")
    
    class Meta:
        unique_together = ('role_matrix', 'skill')
        ordering = ['skill__name']
    
    def __str__(self):
        return f"{self.role_matrix.title} - {self.skill.name} (Level {self.required_level})"


class SkillMatrix(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave'),
    ]

    # Roster identity (name/email/join_date) lives on employees.Employee -- the same record
    # Planner/Tracker/Workforce use -- so this app never maintains a second, driftable copy.
    # `status` stays here rather than deferring to Employee.is_active: it's a richer,
    # skill-tracking-specific state (e.g. "on_leave") distinct from whether someone is
    # employed at all.
    employee = models.OneToOneField('employees.Employee', on_delete=models.CASCADE, related_name='skill_matrix')
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')
    role_matrix = models.ForeignKey(RoleMatrix, on_delete=models.SET_NULL, null=True, blank=True, help_text="Assigned Role")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    class Meta:
        ordering = ['employee__name']

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.employee.name

    @property
    def email(self):
        return self.employee.email

    @property
    def join_date(self):
        return self.employee.join_date

    @property
    def is_active(self):
        return self.status == 'active'
    
    def get_skill_count(self):
        return self.skills.count()
    
    def get_assessed_skills(self):
        return self.skills.select_related('skill').all()
    
    def get_required_benchmarks(self):
        if self.role_matrix:
            return self.role_matrix.benchmarks.select_related('skill').all()
        return SkillBenchmark.objects.none()

    def has_benchmarks(self):
        return bool(self.role_matrix and self.role_matrix.benchmarks.exists())

    def get_missing_benchmarks(self):
        if not self.role_matrix:
            return Skill.objects.none()
        required_skills = set(b.skill.id for b in self.role_matrix.benchmarks.all())
        recorded_skills = set(s.skill.id for s in self.skills.all())
        missing = required_skills - recorded_skills
        return Skill.objects.filter(id__in=missing)
    
    def get_skill_gap_data(self):
        gaps = []
        benchmarks = self.get_required_benchmarks()
        
        if not benchmarks:
            return []
        
        for benchmark in benchmarks:
            emp_skill = self.skills.filter(skill=benchmark.skill).first()
            actual_level = emp_skill.actual_level if emp_skill else 0
            gap = benchmark.required_level - actual_level

            gaps.append({
                'skill': benchmark.skill,
                'required_level': benchmark.required_level,
                'actual_level': actual_level,
                'gap': gap,
                'weight': gap_weight(benchmark.is_mandatory),
                'status': 'met' if gap <= 0 else ('warning' if gap <= 1 else 'critical'),
                'emp_skill': emp_skill,
            })

        return gaps

    def get_skills_needing_training(self):
        return [g for g in self.get_skill_gap_data() if g['gap'] > 0]

    def get_overall_gap_score(self):
        gaps = self.get_skill_gap_data()
        if not gaps:
            return 0
        total_weight = sum(g['weight'] for g in gaps)
        return sum(g['gap'] * g['weight'] for g in gaps) / total_weight
    
    def get_skills_met_percentage(self):
        gaps = self.get_skill_gap_data()
        if not gaps:
            return 0
        met = sum(1 for g in gaps if g['gap'] <= 0)
        return round((met / len(gaps)) * 100)

    def get_skill_history(self):
        """Per-skill chronological level history.

        EmployeeSkillHistory only gets a row when a level *changes* (see
        EmployeeSkill.save() below), so a skill rated once and never touched again
        has zero history rows. The current EmployeeSkill row is folded in as the
        latest point so every skill still has at least one data point.
        """
        points_by_skill = defaultdict(list)

        for h in self.skill_history.select_related('skill').order_by('evaluated_on'):
            points_by_skill[h.skill.name].append({
                'date': h.evaluated_on.date().isoformat(),
                'level': h.recorded_level,
            })

        for es in self.skills.select_related('skill').all():
            current_point = {'date': es.last_evaluated.isoformat(), 'level': es.actual_level}
            points = points_by_skill[es.skill.name]
            if not points or points[-1]['date'] != current_point['date']:
                points.append(current_point)

        history = {}
        for skill_name, points in points_by_skill.items():
            points.sort(key=lambda p: p['date'])
            deduped = []
            for point in points:
                if deduped and deduped[-1]['date'] == point['date']:
                    deduped[-1] = point
                else:
                    deduped.append(point)
            history[skill_name] = deduped

        return history

class EmployeeSkill(models.Model):
    RATING_STATUS_CHOICES = [
        ('none', 'No Self-Rating'),
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('overridden', 'Overridden'),
    ]

    skill_matrix = models.ForeignKey(SkillMatrix, on_delete=models.CASCADE, related_name='skills')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='employee_skills')
    actual_level = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    notes = models.TextField(blank=True, null=True)
    last_evaluated = models.DateField(auto_now=True)

    # Self vs. manager rating: the employee's own assessment, pending manager approval.
    # actual_level above remains the single official value used in every gap calculation.
    self_rated_level = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    self_rated_on = models.DateField(null=True, blank=True)
    rating_status = models.CharField(max_length=20, choices=RATING_STATUS_CHOICES, default='none')

    class Meta:
        unique_together = ('skill_matrix', 'skill')
        ordering = ['skill__name']

    def __str__(self):
        return f"{self.skill_matrix.name} - {self.skill.name}: {self.actual_level}"

    @property
    def employee(self):
        return self.skill_matrix

    @property
    def rating_gap(self):
        if self.self_rated_level is None:
            return None
        return self.self_rated_level - self.actual_level

    @property
    def has_active_development_plan(self):
        """A development plan a manager hasn't yet marked Completed/Cancelled blocks
        approving this skill's self-rating — the gap it was raised for isn't considered
        closed just because the employee re-rated themselves higher."""
        return DevelopmentPlan.objects.filter(
            skill_matrix_id=self.skill_matrix_id, skill_id=self.skill_id,
        ).exclude(status__in=['completed', 'cancelled']).exists()

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_level = None if is_new else EmployeeSkill.objects.get(pk=self.pk).actual_level
        
        super().save(*args, **kwargs)
        
        if not is_new and old_level != self.actual_level:
            EmployeeSkillHistory.objects.create(
                skill_matrix=self.skill_matrix,
                skill=self.skill,
                recorded_level=self.actual_level,
            )

class EmployeeSkillHistory(models.Model):
    skill_matrix = models.ForeignKey(SkillMatrix, on_delete=models.CASCADE, related_name='skill_history')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    recorded_level = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    evaluated_on = models.DateTimeField(auto_now_add=True)
    evaluated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    @property
    def employee(self):
        return self.skill_matrix
    
    class Meta:
        ordering = ['-evaluated_on']
    
    def __str__(self):
        return f"{self.employee.name} - {self.skill.name}: {self.recorded_level} on {self.evaluated_on}"


class DevelopmentPlan(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    skill_matrix = models.ForeignKey(SkillMatrix, on_delete=models.CASCADE, related_name='development_plans')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='development_plans')
    action = models.CharField(max_length=255, help_text="e.g. 'Complete Django REST course', 'Pair with a senior dev'")
    resource_url = models.URLField(blank=True, null=True, help_text="Optional link to a course or resource")
    target_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.skill_matrix.name} - {self.skill.name}: {self.action}"

    @property
    def is_overdue(self):
        if not self.target_date or self.status in ('completed', 'cancelled'):
            return False
        return self.target_date < timezone.now().date()
