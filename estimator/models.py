from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models


class Activity(models.Model):
    """A standard engineering activity performed on every project (e.g. Programming,
    Commissioning). The master list rows of the Module x Activity time matrix."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class ModuleType(models.Model):
    """A category of physical module (Transfer Conveyor, Merge, Divert, ...). The
    master list columns of the Module x Activity time matrix."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def has_configured_times(self):
        return self.activity_times.exists()

    def configured_segments(self):
        return Segment.objects.filter(activity_times__module_type=self).distinct().order_by('name')


class Segment(models.Model):
    """An application area a module type is used within (e.g. Case Handling, Pallet
    Conveying). The same module type can appear in several segments with a different
    time matrix in each -- a Transfer Conveyor in Case Handling isn't necessarily the
    same effort as one in Pallet Conveying."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ModuleActivityTime(models.Model):
    """One cell of the Segment x Module Type x Activity time matrix: how many minutes
    a single module of `module_type`, used within `segment`, takes to complete
    `activity`.

    `minutes` is always the effective per-module rate used by calculations. It can be
    entered directly (single-module mode) or derived from a batch entry (`batch_count`
    modules take `batch_minutes` total) when the admin knows the bulk figure but not the
    per-unit rate -- e.g. "10 Transfer Conveyors take 20 min of Programming" -> minutes
    = 2.0. Exactly one of the two entry modes is used per cell; `save()` derives
    `minutes` from the batch fields whenever both are present.
    """

    segment = models.ForeignKey(Segment, on_delete=models.CASCADE, related_name='activity_times')
    module_type = models.ForeignKey(ModuleType, on_delete=models.CASCADE, related_name='activity_times')
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='module_times')
    minutes = models.DecimalField(max_digits=7, decimal_places=1, default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])
    batch_count = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
        help_text="Batch entry mode: this many modules together take batch_minutes.",
    )
    batch_minutes = models.DecimalField(
        max_digits=8, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))],
        help_text="Batch entry mode: total minutes for batch_count modules.",
    )

    class Meta:
        unique_together = ('segment', 'module_type', 'activity')
        ordering = ['segment__name', 'module_type__name', 'activity__display_order']

    def __str__(self):
        return f"{self.segment.name} / {self.module_type.name} - {self.activity.name}: {self.minutes} min"

    def save(self, *args, **kwargs):
        if self.batch_count and self.batch_minutes is not None:
            self.minutes = self.batch_minutes / self.batch_count
        super().save(*args, **kwargs)


class ComplexityLevel(models.Model):
    """A multiplier preset (Low/Medium/High, editable) applied to base estimates."""

    name = models.CharField(max_length=50, unique=True)
    multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1.00'), validators=[MinValueValidator(Decimal('0.01'))])
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'multiplier']

    def __str__(self):
        return f"{self.name} (x{self.multiplier})"


class Project(models.Model):
    """A named pre-sales project/quote made up of module line items."""

    name = models.CharField(max_length=200)
    customer = models.CharField(max_length=200, blank=True, null=True)
    complexity = models.ForeignKey(ComplexityLevel, on_delete=models.PROTECT, related_name='projects')
    notes = models.TextField(blank=True, null=True)
    minutes_per_working_day = models.PositiveIntegerField(
        default=480, validators=[MinValueValidator(1)],
        help_text="Working minutes in a day, used to convert the total estimate to man-days.",
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='estimator_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class ProjectModule(models.Model):
    """One module line item on a project: a module type (used within a segment) and
    how many of it."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='modules')
    segment = models.ForeignKey(Segment, on_delete=models.PROTECT, related_name='project_modules')
    module_type = models.ForeignKey(ModuleType, on_delete=models.PROTECT, related_name='project_modules')
    count = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    complexity_override = models.ForeignKey(
        ComplexityLevel, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
        help_text="Optional. Overrides the project's complexity for this module line only.",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.project.name} - {self.segment.name} / {self.module_type.name} x{self.count}"

    @property
    def effective_complexity(self):
        return self.complexity_override or self.project.complexity
