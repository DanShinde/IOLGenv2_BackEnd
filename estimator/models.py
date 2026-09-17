from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models


class ActivityCategory(models.TextChoices):
    DEV_TESTING = 'dev_testing', 'Development & Testing'
    ONSITE_COMMISSIONING = 'onsite_commissioning', 'On-Site Commissioning'


class Activity(models.Model):
    """A standard engineering activity performed on every project (e.g. Programming,
    Commissioning). The master list rows of the Module x Activity time matrix.

    Every activity belongs to one of two fixed categories, so effort can be reported
    separately for office-side Development & Testing work versus field-side On-Site
    Commissioning work."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=25, choices=ActivityCategory.choices, default=ActivityCategory.DEV_TESTING)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['category', 'display_order', 'name']

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


class TimeUnit(models.TextChoices):
    SECONDS = 'sec', 'Seconds'
    MINUTES = 'min', 'Minutes'
    HOURS = 'hour', 'Hours'
    DAYS = 'day', 'Days'


# Fixed unit -> minutes factors. DAYS is deliberately absent: its length depends on
# whichever project the estimate is being computed for (Project.minutes_per_working_day),
# so it's resolved dynamically in effective_minutes() instead of being fixed here.
_FIXED_UNIT_TO_MINUTES = {
    TimeUnit.SECONDS: Decimal('1') / Decimal('60'),
    TimeUnit.MINUTES: Decimal('1'),
    TimeUnit.HOURS: Decimal('60'),
}

DEFAULT_MINUTES_PER_WORKING_DAY = 480


class ModuleActivityTime(models.Model):
    """One cell of the Segment x Module Type x Activity time matrix: how much time a
    single module of `module_type`, used within `segment`, takes to complete
    `activity`.

    Entered in whichever `unit` is most convenient (seconds/minutes/hours/days) and in
    either single-module mode (`value`) or batch mode (`batch_count` modules take
    `batch_value` total, for when the admin knows the bulk figure but not the per-unit
    rate -- e.g. "10 Transfer Conveyors take 20 min of Programming"). Exactly one of the
    two entry modes is used per cell.

    Nothing is pre-converted to minutes and stored: a 'day' means a different number of
    minutes on different projects (each has its own minutes_per_working_day), so the
    actual per-module minutes for a given project are only resolved by
    `effective_minutes()` at estimate-calculation time.
    """

    segment = models.ForeignKey(Segment, on_delete=models.CASCADE, related_name='activity_times')
    module_type = models.ForeignKey(ModuleType, on_delete=models.CASCADE, related_name='activity_times')
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='module_times')
    unit = models.CharField(max_length=10, choices=TimeUnit.choices, default=TimeUnit.MINUTES)
    value = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))],
        help_text="Single-module entry mode: time for one module, in `unit`.",
    )
    batch_count = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
        help_text="Batch entry mode: this many modules together take batch_value.",
    )
    batch_value = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0'))],
        help_text="Batch entry mode: total time for batch_count modules, in `unit`.",
    )
    remark = models.TextField(
        blank=True, null=True,
        help_text="Reference note on how this time was arrived at (e.g. a vendor spec sheet or past project). "
                   "Internal use only -- never shown on the project report, PDF, or Excel export.",
    )

    class Meta:
        unique_together = ('segment', 'module_type', 'activity')
        ordering = ['segment__name', 'module_type__name', 'activity__display_order']

    def __str__(self):
        return f"{self.segment.name} / {self.module_type.name} - {self.activity.name}"

    def effective_minutes(self, minutes_per_working_day=DEFAULT_MINUTES_PER_WORKING_DAY):
        """The per-module minutes this cell contributes, resolved for a specific
        project's working-day length (only relevant when unit == 'day')."""
        factor = Decimal(minutes_per_working_day) if self.unit == TimeUnit.DAYS else _FIXED_UNIT_TO_MINUTES[self.unit]

        if self.batch_count and self.batch_value is not None:
            return (self.batch_value * factor) / self.batch_count
        if self.value is not None:
            return self.value * factor
        return Decimal('0')


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

    name = models.CharField(max_length=200, unique=True)
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
    zone = models.CharField(
        max_length=150, blank=True, default='',
        help_text="Optional line/zone label (e.g. from an imported module list). Rows are grouped by this "
                   "on the estimate to calculate effort separately per zone within the project.",
    )
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


class ProjectTemplate(models.Model):
    """A reusable, named combination of module lines (segment + module type + count +
    complexity override) that a new Project can be started from, or that an existing
    Project's current module list can be saved as. Independent of any specific Project
    -- editing or deleting a Project later never touches templates made from it."""

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, null=True)
    complexity = models.ForeignKey(ComplexityLevel, on_delete=models.PROTECT, related_name='templates')
    minutes_per_working_day = models.PositiveIntegerField(default=480, validators=[MinValueValidator(1)])
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='estimator_templates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ProjectTemplateModule(models.Model):
    """One module line item on a template: a module type (used within a segment) and
    how many of it -- the template's counterpart to ProjectModule.

    Unlike a real Project's module rows, `count` may be 0 here: a template mainly
    captures *which* module type/segment combinations typically go together, since the
    actual quantity varies project to project. A 0-count row is a placeholder the user
    fills in with the real quantity once a project is started from this template --
    ProjectModule (the project side) still requires count >= 1."""

    template = models.ForeignKey(ProjectTemplate, on_delete=models.CASCADE, related_name='modules')
    segment = models.ForeignKey(Segment, on_delete=models.PROTECT, related_name='template_modules')
    module_type = models.ForeignKey(ModuleType, on_delete=models.PROTECT, related_name='template_modules')
    count = models.PositiveIntegerField(default=1, validators=[MinValueValidator(0)])
    complexity_override = models.ForeignKey(
        ComplexityLevel, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
        help_text="Optional. Overrides the template's complexity for this module line only.",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.template.name} - {self.segment.name} / {self.module_type.name} x{self.count}"


class ModuleNameAlias(models.Model):
    """A remembered mapping from a raw Module Name string (exactly as it appears in an
    uploaded sheet) to the standard ModuleType a user has confirmed it means. Learned
    automatically the first time a raw name is mapped during an import's review step --
    no guessing involved, so future imports of the same raw name auto-fill exactly what
    was confirmed before rather than a fuzzy best-guess. If a later import maps the same
    raw name to a *different* ModuleType, the user is asked whether to update this
    alias for future imports too, or just use the new mapping for that one import."""

    raw_name_normalized = models.CharField(max_length=200, unique=True, help_text="raw_name.strip().lower(), used for lookup.")
    raw_name = models.CharField(max_length=200, help_text="Display form of the raw name, as most recently seen.")
    module_type = models.ForeignKey(ModuleType, on_delete=models.CASCADE, related_name='name_aliases')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['raw_name']

    def __str__(self):
        return f"{self.raw_name} -> {self.module_type.name}"


class ModuleImportRow(models.Model):
    """One row of an in-progress module-list import, staged for the user to correct
    (module type match, zone, segment, count) before being committed to real
    ProjectModule rows. A fresh upload for a project clears any rows left over from a
    prior, abandoned upload. Never contributes to the project's estimate itself --
    only the ProjectModule rows created from it (on confirm) do."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='import_rows')
    row_number = models.PositiveIntegerField(help_text="The row's position in the uploaded sheet, for reference.")
    sr = models.CharField(max_length=50, blank=True, help_text="Sr. No. from the sheet, for reference only.")
    raw_module_name = models.CharField(max_length=200, blank=True, help_text="Module Name exactly as read from the sheet.")
    module_no = models.CharField(max_length=100, blank=True, help_text="Module No. from the sheet, for reference only.")
    floor_level = models.CharField(max_length=50, blank=True, help_text="Floor Level from the sheet, for reference only.")
    zone = models.CharField(max_length=150, blank=True, default='', help_text="From the sheet's Line/Zone column; editable.")
    module_type = models.ForeignKey(
        ModuleType, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        help_text="Matched via an exact name match or a previously-saved ModuleNameAlias, or user-corrected. "
                   "Blank means unmatched -- must be set before this row can be confirmed. Never a fuzzy guess.",
    )
    segment = models.ForeignKey(
        Segment, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        help_text="Not present in the sheet -- the user must choose one before this row can be confirmed.",
    )
    count = models.PositiveIntegerField(default=0, help_text="0 means unresolved -- must be corrected to 1 or more before this row can be confirmed.")

    class Meta:
        ordering = ['row_number']

    def __str__(self):
        return f"{self.project.name} import row {self.row_number}: {self.raw_module_name}"

    @property
    def is_valid(self):
        return self.module_type_id is not None and self.segment_id is not None and self.count >= 1
