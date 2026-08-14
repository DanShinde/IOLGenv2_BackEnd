# planner/models.py

from django.db import models
from django.utils import timezone
from datetime import timedelta
from .utils import calculate_end_date, count_working_days, next_working_day
from employees.models import Employee
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

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

class ActivityHeading(models.Model):
    """A named grouping of a project's activities (e.g. 'Offline Development'), purely
    organizational -- start/end dates are derived from member activities at render time
    (see activity_planner_view), never stored, so there's nothing to keep in sync here."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='headings')
    name = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f"{self.project.project_id} - {self.name}"

class Activity(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    activity_name = models.CharField(max_length=200)
    project_type = models.ForeignKey(ProjectType, on_delete=models.SET_NULL, null=True, blank=True)
    assignee = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True, blank=True)
    heading = models.ForeignKey(ActivityHeading, on_delete=models.SET_NULL, null=True, blank=True, related_name='activities')
    remark = models.TextField(blank=True)
    start_date = models.DateField(default=timezone.now)
    duration = models.PositiveIntegerField(default=1, help_text="Duration in working days")
    end_date = models.DateField(blank=True, null=True)
    completion_percentage = models.PositiveSmallIntegerField(default=0, help_text="Percent complete (0-100)")
    is_completed = models.BooleanField(default=False)
    predecessor = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='successors',
        help_text="This activity's start date is derived from this predecessor's finish date."
    )

    def __str__(self):
        return f"{self.project.project_id} - {self.activity_name}"

    def save(self, *args, _cascade_visited=None, **kwargs):
        # _cascade_visited is only ever passed by this method's own recursive cascade call
        # below (never by Django or any external caller), so every normal .save() still
        # behaves exactly as before -- it just also cascades to any linked successors now.
        top_level = _cascade_visited is None
        if top_level:
            _cascade_visited = set()

        # Defensive clamp only — the 100% <-> completed sync itself is handled where the
        # user actually changes one of the two fields (activity_quick_update_view), not
        # here, so that e.g. unchecking "completed" while % is still 100 isn't immediately
        # flipped back by an unrelated save().
        self.completion_percentage = max(0, min(100, self.completion_percentage or 0))

        # 1. Get Global Holidays
        holidays = list(Holiday.objects.values_list('date', flat=True))

        # While linked, start_date is a derived field (like end_date below) -- it always
        # follows the next working day after the predecessor's finish date, so manual edits
        # to start_date on a linked activity have no lasting effect. Unlink first to move it
        # independently. end_date is cleared here (mirroring how start_date/duration edits
        # clear it in activity_quick_update_view) so it re-derives from duration below,
        # instead of the stale stored end_date being mistaken for a manual override.
        if self.predecessor_id and self.predecessor.end_date:
            self.start_date = next_working_day(self.predecessor.end_date, holidays)
            self.end_date = None

        # 2. Get Assignee Leaves (if assigned)
        assignee_leaves = []
        if self.assignee:
            # We only care about leaves that happen on or after the activity start
            relevant_leaves = self.assignee.planner_leaves.filter(end_date__gte=self.start_date)
            for leave in relevant_leaves:
                # Expand range to individual dates
                curr = leave.start_date
                while curr <= leave.end_date:
                    assignee_leaves.append(curr)
                    curr += timedelta(days=1)
        
        # 3. Logic: If End Date is provided (manual override), recalculate Duration.
        #    Otherwise, calculate End Date from Duration.
        if self.end_date:
            # Ensure End Date is not before Start Date
            if self.end_date < self.start_date:
                self.end_date = self.start_date
                
            # Recalculate duration based on start_date and end_date
            # count_working_days returns total working days (excluding weekends/holidays)
            raw_duration = count_working_days(self.start_date, self.end_date, holidays)
            
            # Subtract assignee leaves that fall on working days
            leaves_overlap = 0
            for leave_date in assignee_leaves:
                if self.start_date <= leave_date <= self.end_date:
                    # Check if leave_date is a working day (Mon-Fri and not a holiday)
                    if leave_date.weekday() < 5 and leave_date not in holidays:
                        leaves_overlap += 1
            
            # Ensure duration is at least 1
            self.duration = max(1, raw_duration - leaves_overlap)
        else:
            # Standard behavior: Calculate End Date from Duration
            self.end_date = calculate_end_date(self.start_date, self.duration, holidays, assignee_leaves)

        super().save(*args, **kwargs)

        # Cascade this activity's (possibly new) end_date forward to anything linked to it.
        # _cascade_visited guards against a corrupt/circular chain looping forever; it's
        # shared across the whole recursive walk so each activity is only re-saved once.
        _cascade_visited.add(self.pk)
        cascade_updates = []
        for successor in self.successors.exclude(pk__in=_cascade_visited).select_related('predecessor'):
            successor.save(_cascade_visited=_cascade_visited)
            cascade_updates.append(successor)
            cascade_updates.extend(getattr(successor, '_cascade_updates', []))
        # Stashed on the instance (not returned) so save() keeps Django's normal signature/
        # return value -- callers that care (the quick-update / link endpoints) read it off
        # the instance right after calling save(), everyone else can ignore it.
        self._cascade_updates = cascade_updates

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

class Site(models.Model):
    name = models.CharField(max_length=200, blank=True)
    project = models.OneToOneField(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='site_record')
    location = models.CharField(max_length=200)
    is_office = models.BooleanField(default=False, verbose_name="Is Office Location")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        code = self.project.project_id if self.project else "Office"
        return f"{self.name} ({code})"
    
    def save(self, *args, **kwargs):
        # Auto-populate name from project
        if self.project:
            self.name = self.project.customer_name

        # Geocode if location has changed or if coordinates are missing
        try:
            old_instance = Site.objects.get(pk=self.pk)
            location_changed = old_instance.location != self.location
        except Site.DoesNotExist:
            location_changed = True # It's a new instance

        if self.location and (location_changed or self.latitude is None or self.longitude is None):
            try:
                geolocator = Nominatim(user_agent="iolgen_planner_app", timeout=10)
                location_data = geolocator.geocode(self.location)
                if location_data:
                    self.latitude = location_data.latitude
                    self.longitude = location_data.longitude
            except (GeocoderTimedOut, GeocoderUnavailable):
                # Don't block saving if the geocoding service is unavailable
                pass

        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ['name']

class SiteAllocation(models.Model):
    employee = models.ForeignKey('employees.Employee', on_delete=models.CASCADE, related_name='site_allocations')
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='allocations')
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    
    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.employee} at {self.site}"

    @property
    def duration_days(self):
        end = self.end_date if self.end_date else timezone.now().date()
        return (end - self.start_date).days

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