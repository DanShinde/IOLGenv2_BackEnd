import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .calculations import build_project_estimate
from .exports import render_project_report_excel, render_project_report_pdf
from .forms import (
    ActivityForm, ComplexityLevelForm, ModuleTypeForm, ProjectForm, ProjectTemplateForm,
    SaveProjectAsTemplateForm, SegmentForm,
)
from .imports import ModuleListParseError, match_module_type, normalize_name, parse_module_list
from .mixins import CancelUrlMixin, ProtectedDeleteMixin, StaffRequiredMixin
from .models import (
    Activity, ComplexityLevel, ModuleActivityTime, ModuleImportRow, ModuleNameAlias, ModuleType,
    Project, ProjectModule, ProjectTemplate, ProjectTemplateModule, Segment, TimeUnit,
)


def unique_name(model, base_name, exclude_pk=None):
    """Returns `base_name` if it's free, otherwise `base_name (2)`, `base_name (3)`, ...
    -- used wherever a name is generated rather than typed (duplicate, save-as-template),
    since those flows can't rely on form validation to catch a collision."""

    def _taken(candidate):
        qs = model.objects.filter(name__iexact=candidate)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        return qs.exists()

    if not _taken(base_name):
        return base_name
    counter = 2
    while _taken(f'{base_name} ({counter})'):
        counter += 1
    return f'{base_name} ({counter})'


def safe_json(data):
    """json.dumps() with <, >, & escaped, for embedding directly inside a <script> tag."""
    return json.dumps(data).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


# --------------------------------------------------------------------------- Activities

class ActivityListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = Activity
    template_name = 'estimator/activity_list.html'
    context_object_name = 'activities'


class ActivityCreateView(LoginRequiredMixin, StaffRequiredMixin, CancelUrlMixin, CreateView):
    model = Activity
    form_class = ActivityForm
    template_name = 'estimator/add_form.html'
    success_url = reverse_lazy('estimator_activity_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Activity'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Activity "{form.instance.name}" added.')
        return super().form_valid(form)


class ActivityUpdateView(LoginRequiredMixin, StaffRequiredMixin, CancelUrlMixin, UpdateView):
    model = Activity
    form_class = ActivityForm
    template_name = 'estimator/add_form.html'
    success_url = reverse_lazy('estimator_activity_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Activity'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Activity "{form.instance.name}" updated.')
        return super().form_valid(form)


class ActivityDeleteView(LoginRequiredMixin, StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = Activity
    template_name = 'estimator/confirm_delete.html'
    success_url = reverse_lazy('estimator_activity_list')
    protected_message = "Can't delete -- this activity still has time entries in a module's matrix."


# --------------------------------------------------------------------------- Module Types

class ModuleTypeListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = ModuleType
    template_name = 'estimator/module_type_list.html'
    context_object_name = 'module_types'


class ModuleTypeCreateView(LoginRequiredMixin, StaffRequiredMixin, CancelUrlMixin, CreateView):
    model = ModuleType
    form_class = ModuleTypeForm
    template_name = 'estimator/add_form.html'
    success_url = reverse_lazy('estimator_module_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Module Type'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Module type "{form.instance.name}" added.')
        return super().form_valid(form)


class ModuleTypeUpdateView(LoginRequiredMixin, StaffRequiredMixin, CancelUrlMixin, UpdateView):
    model = ModuleType
    form_class = ModuleTypeForm
    template_name = 'estimator/add_form.html'
    success_url = reverse_lazy('estimator_module_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Module Type'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Module type "{form.instance.name}" updated.')
        return super().form_valid(form)


class ModuleTypeDeleteView(LoginRequiredMixin, StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = ModuleType
    template_name = 'estimator/confirm_delete.html'
    success_url = reverse_lazy('estimator_module_type_list')
    protected_message = "Can't delete -- this module type is used by one or more projects."


class ModuleTypeSegmentsView(LoginRequiredMixin, StaffRequiredMixin, TemplateView):
    """Lists which Segments already have a time matrix configured for this Module Type
    (a Transfer Conveyor can be configured separately for Case Handling and for Pallet
    Conveying), plus lets the admin start configuring a segment it doesn't have yet."""

    template_name = 'estimator/module_type_segments.html'

    def get_module_type(self):
        return get_object_or_404(ModuleType, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module_type = self.get_module_type()
        configured_ids = set(module_type.activity_times.values_list('segment_id', flat=True))
        context['module_type'] = module_type
        context['configured_segments'] = Segment.objects.filter(id__in=configured_ids).order_by('name')
        context['unconfigured_segments'] = Segment.objects.exclude(id__in=configured_ids).order_by('name')
        return context


class ModuleTypeMatrixView(LoginRequiredMixin, StaffRequiredMixin, TemplateView):
    """The Module Configuration grid for one (Module Type, Segment) combination: every
    Activity as a row with an editable time entry ('N modules take X total', where a
    single-module time is just N=1) and a unit (seconds/minutes/hours/days). Saved in
    one bulk POST."""

    template_name = 'estimator/module_type_matrix.html'

    def get_module_type(self):
        return get_object_or_404(ModuleType, pk=self.kwargs['module_type_pk'])

    def get_segment(self):
        return get_object_or_404(Segment, pk=self.kwargs['segment_pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module_type = self.get_module_type()
        segment = self.get_segment()
        existing = {t.activity_id: t for t in ModuleActivityTime.objects.filter(module_type=module_type, segment=segment)}

        def batch_fields(t):
            # Legacy rows saved via the old single-module field only have `value` set;
            # show them as an equivalent 1-module batch so they still populate the form.
            if t.batch_count and t.batch_value is not None:
                return t.batch_count, t.batch_value
            if t.value is not None:
                return 1, t.value
            return '', ''

        context['module_type'] = module_type
        context['segment'] = segment
        context['time_units'] = TimeUnit.choices
        context['rows'] = []
        for a in Activity.objects.order_by('category', 'display_order', 'name'):
            t = existing.get(a.id)
            batch_count, batch_value = batch_fields(t) if t else ('', '')
            context['rows'].append({
                'activity': a,
                'unit': t.unit if t else TimeUnit.MINUTES,
                'batch_count': batch_count,
                'batch_value': batch_value,
                'remark': t.remark if t else '',
            })
        return context

    def post(self, request, *args, **kwargs):
        module_type = self.get_module_type()
        segment = self.get_segment()
        valid_units = {choice for choice, _ in TimeUnit.choices}

        for activity in Activity.objects.all():
            unit = request.POST.get(f'unit_{activity.id}', TimeUnit.MINUTES).strip()
            if unit not in valid_units:
                unit = TimeUnit.MINUTES
            batch_count_raw = request.POST.get(f'batch_count_{activity.id}', '').strip()
            batch_value_raw = request.POST.get(f'batch_value_{activity.id}', '').strip()
            remark = request.POST.get(f'remark_{activity.id}', '').strip()

            if not batch_count_raw and not batch_value_raw:
                # No time entered -- still worth saving if there's a remark to keep
                # (e.g. a reference note on a cell that isn't configured yet).
                if remark:
                    ModuleActivityTime.objects.update_or_create(
                        module_type=module_type, segment=segment, activity=activity,
                        defaults={'remark': remark},
                    )
                continue

            if not batch_count_raw or not batch_value_raw:
                messages.error(request, f"'{activity.name}': needs both a module count and a total time -- row skipped.")
                continue
            try:
                batch_count = int(batch_count_raw)
                batch_value = float(batch_value_raw)
            except ValueError:
                messages.error(request, f"Ignored invalid value for '{activity.name}'.")
                continue
            if batch_count < 1 or batch_value < 0:
                messages.error(request, f"Ignored invalid value for '{activity.name}'.")
                continue
            ModuleActivityTime.objects.update_or_create(
                module_type=module_type, segment=segment, activity=activity,
                defaults={'unit': unit, 'value': None, 'batch_count': batch_count, 'batch_value': batch_value, 'remark': remark},
            )

        messages.success(request, f'Time matrix for "{module_type.name}" / "{segment.name}" saved.')
        return redirect('estimator_module_type_matrix', module_type_pk=module_type.pk, segment_pk=segment.pk)


# --------------------------------------------------------------------------- Segments

class SegmentListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = Segment
    template_name = 'estimator/segment_list.html'
    context_object_name = 'segments'


class SegmentCreateView(LoginRequiredMixin, StaffRequiredMixin, CancelUrlMixin, CreateView):
    model = Segment
    form_class = SegmentForm
    template_name = 'estimator/add_form.html'
    success_url = reverse_lazy('estimator_segment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Segment'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Segment "{form.instance.name}" added.')
        return super().form_valid(form)


class SegmentUpdateView(LoginRequiredMixin, StaffRequiredMixin, CancelUrlMixin, UpdateView):
    model = Segment
    form_class = SegmentForm
    template_name = 'estimator/add_form.html'
    success_url = reverse_lazy('estimator_segment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Segment'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Segment "{form.instance.name}" updated.')
        return super().form_valid(form)


class SegmentDeleteView(LoginRequiredMixin, StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = Segment
    template_name = 'estimator/confirm_delete.html'
    success_url = reverse_lazy('estimator_segment_list')
    protected_message = "Can't delete -- this segment is used by one or more projects or time matrices."


# --------------------------------------------------------------------------- Complexity Levels

class ComplexityListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = ComplexityLevel
    template_name = 'estimator/complexity_list.html'
    context_object_name = 'complexity_levels'


class ComplexityCreateView(LoginRequiredMixin, StaffRequiredMixin, CancelUrlMixin, CreateView):
    model = ComplexityLevel
    form_class = ComplexityLevelForm
    template_name = 'estimator/add_form.html'
    success_url = reverse_lazy('estimator_complexity_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Complexity Level'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Complexity level "{form.instance.name}" added.')
        return super().form_valid(form)


class ComplexityUpdateView(LoginRequiredMixin, StaffRequiredMixin, CancelUrlMixin, UpdateView):
    model = ComplexityLevel
    form_class = ComplexityLevelForm
    template_name = 'estimator/add_form.html'
    success_url = reverse_lazy('estimator_complexity_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Complexity Level'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Complexity level "{form.instance.name}" updated.')
        return super().form_valid(form)


class ComplexityDeleteView(LoginRequiredMixin, StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = ComplexityLevel
    template_name = 'estimator/confirm_delete.html'
    success_url = reverse_lazy('estimator_complexity_list')
    protected_message = "Can't delete -- this complexity level is used by one or more projects."


# --------------------------------------------------------------------------- Projects

class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'estimator/project_list.html'
    context_object_name = 'projects'

    def get_queryset(self):
        qs = Project.objects.select_related('complexity', 'created_by')
        if not self.request.user.is_staff:
            qs = qs.filter(created_by=self.request.user)
        return qs


class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'estimator/add_form.html'

    def get_initial(self):
        initial = super().get_initial()
        template_id = self.request.GET.get('template')
        if template_id:
            initial['start_from_template'] = template_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'New Project'
        context['cancel_url'] = reverse('estimator_project_list')
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        # Must be set before super().form_valid() runs -- it builds the redirect via
        # get_success_url() internally, which reads this flag.
        template = form.cleaned_data.get('start_from_template')
        self._started_from_template = bool(template)
        with transaction.atomic():
            response = super().form_valid(form)
            if template:
                ProjectModule.objects.bulk_create([
                    ProjectModule(
                        project=self.object,
                        segment=tm.segment,
                        module_type=tm.module_type,
                        count=tm.count,
                        complexity_override=tm.complexity_override,
                        order=tm.order,
                    )
                    for tm in template.modules.all()
                ])
                messages.success(self.request, f'Project "{form.instance.name}" created from template "{template.name}".')
            else:
                messages.success(self.request, f'Project "{form.instance.name}" created. Next, import a module list or add rows manually.')
        return response

    def get_success_url(self):
        # A project started from a template already has its module rows, so it goes
        # straight to the builder like before. An empty project goes to the import
        # wizard's upload step instead -- that's what makes "New Project" a wizard
        # (Details -> Upload -> Review -> Calculated) rather than a bare empty grid.
        if self._started_from_template:
            return reverse('estimator_project_builder', args=[self.object.pk])
        return reverse('estimator_project_import_upload', args=[self.object.pk])


class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'estimator/add_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Project'
        context['cancel_url'] = reverse('estimator_project_builder', args=[self.object.pk])
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Project "{form.instance.name}" updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('estimator_project_builder', args=[self.object.pk])


class ProjectDeleteView(LoginRequiredMixin, DeleteView):
    model = Project
    template_name = 'estimator/confirm_delete.html'
    success_url = reverse_lazy('estimator_project_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        label = self.object.name
        self.object.delete()
        messages.success(request, f'Project "{label}" deleted.')
        return redirect(self.success_url)


class ProjectDetailView(LoginRequiredMixin, DetailView):
    """The Project Builder / Estimator main screen."""

    model = Project
    template_name = 'estimator/project_builder.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        estimate = build_project_estimate(project)
        context['estimate'] = estimate

        segments = list(Segment.objects.order_by('name'))
        module_types = list(ModuleType.objects.order_by('name'))
        complexity_levels = list(ComplexityLevel.objects.order_by('display_order', 'multiplier'))
        activities = estimate['activities']
        # Resolved for *this* project's own minutes_per_working_day, so a 'day'-unit
        # matrix cell contributes the right number of minutes here even though it isn't
        # a fixed conversion across projects.
        matrix = {
            (t.segment_id, t.module_type_id, t.activity_id): float(t.effective_minutes(project.minutes_per_working_day))
            for t in ModuleActivityTime.objects.all()
        }

        context['segments_json'] = safe_json([{'id': s.id, 'name': s.name} for s in segments])
        context['module_types_json'] = safe_json([{'id': mt.id, 'name': mt.name} for mt in module_types])
        context['complexity_levels_json'] = safe_json([
            {'id': c.id, 'name': c.name, 'multiplier': float(c.multiplier)} for c in complexity_levels
        ])
        context['activities_json'] = safe_json([{'id': a.id, 'name': a.name, 'category': a.category} for a in activities])
        context['matrix_json'] = safe_json({
            f"{seg_id}_{mt_id}_{act_id}": mins for (seg_id, mt_id, act_id), mins in matrix.items()
        })
        context['modules_json'] = safe_json([
            {
                'id': pm.id,
                'segment_id': pm.segment_id,
                'module_type_id': pm.module_type_id,
                'count': pm.count,
                'zone': pm.zone,
                'complexity_override_id': pm.complexity_override_id,
            }
            for pm in project.modules.order_by('order', 'id')
        ])
        context['existing_zones_json'] = safe_json(sorted({
            pm.zone for pm in project.modules.all() if pm.zone
        }))
        context['project_complexity_id'] = project.complexity_id
        context['minutes_per_day'] = project.minutes_per_working_day
        context['has_pending_import'] = project.import_rows.exists()
        return context


@require_POST
def project_modules_sync(request, pk):
    """Persists the Project Builder's module rows in one shot: updates existing rows by
    id, creates rows with a blank id, deletes any row not resubmitted. Raw POST arrays
    (row_id[]/segment[]/module_type[]/count[]/zone[]/complexity_override[]) rather than
    a Django formset, matching this codebase's existing convention for multi-row form
    submission."""

    project = get_object_or_404(Project, pk=pk)

    row_ids = request.POST.getlist('row_id[]')
    segment_ids = request.POST.getlist('segment[]')
    module_type_ids = request.POST.getlist('module_type[]')
    counts = request.POST.getlist('count[]')
    zones = request.POST.getlist('zone[]')
    complexity_override_ids = request.POST.getlist('complexity_override[]')

    kept_ids = set()
    errors = []

    with transaction.atomic():
        for index, module_type_id in enumerate(module_type_ids):
            module_type_id = module_type_id.strip()
            if not module_type_id:
                continue

            segment_id = segment_ids[index].strip() if index < len(segment_ids) else ''
            if not segment_id:
                errors.append(f"Row {index + 1}: segment is required -- skipped.")
                continue

            count_raw = counts[index].strip() if index < len(counts) else ''
            try:
                count = int(count_raw)
            except ValueError:
                count = 0
            if count < 1:
                errors.append(f"Row {index + 1}: count must be at least 1 -- skipped.")
                continue

            complexity_override_id = complexity_override_ids[index].strip() if index < len(complexity_override_ids) else ''
            zone = zones[index].strip() if index < len(zones) else ''
            row_id = row_ids[index].strip() if index < len(row_ids) else ''

            defaults = {
                'segment_id': segment_id,
                'module_type_id': module_type_id,
                'count': count,
                'zone': zone,
                'complexity_override_id': complexity_override_id or None,
                'order': index,
            }

            if row_id:
                ProjectModule.objects.filter(pk=row_id, project=project).update(**defaults)
                kept_ids.add(int(row_id))
            else:
                pm = ProjectModule.objects.create(project=project, **defaults)
                kept_ids.add(pm.id)

        project.modules.exclude(id__in=kept_ids).delete()

    if errors:
        for e in errors:
            messages.error(request, e)
    else:
        messages.success(request, 'Modules saved.')
    return redirect('estimator_project_builder', pk=project.pk)


# --------------------------------------------------------------------------- Module-list import wizard
#
# Step 2 (Upload) and step 3 (Review & Correct) of the project wizard, sitting between
# ProjectCreateView (step 1: project details) and ProjectDetailView (step 4: the
# auto-calculated, per-zone estimate). Staged rows (ModuleImportRow) never feed the
# estimate themselves -- only the real ProjectModule rows created on confirm do.

def project_import_upload(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if request.method == 'POST':
        uploaded_file = request.FILES.get('module_list')
        if not uploaded_file:
            messages.error(request, 'Choose a file to upload.')
            return render(request, 'estimator/project_import_upload.html', {'project': project})

        try:
            parsed_rows = parse_module_list(uploaded_file)
        except ModuleListParseError as exc:
            messages.error(request, str(exc))
            return render(request, 'estimator/project_import_upload.html', {'project': project})

        if not parsed_rows:
            messages.error(request, 'No module rows found in this file.')
            return render(request, 'estimator/project_import_upload.html', {'project': project})

        module_types = list(ModuleType.objects.all())
        # Only ever auto-fills an exact name match or a mapping the user has
        # explicitly confirmed before (see ModuleNameAlias) -- never a fuzzy guess.
        aliases = {a.raw_name_normalized: a.module_type for a in ModuleNameAlias.objects.select_related('module_type')}

        with transaction.atomic():
            # A fresh upload replaces whatever was staged from a previous, abandoned
            # upload for this project -- only one import can be "in progress" at a time.
            project.import_rows.all().delete()
            ModuleImportRow.objects.bulk_create([
                ModuleImportRow(
                    project=project,
                    row_number=r['row_number'],
                    sr=r['sr'],
                    raw_module_name=r['raw_module_name'],
                    module_no=r['module_no'],
                    floor_level=r['floor_level'],
                    zone=r['zone'],
                    module_type=match_module_type(r['raw_module_name'], module_types, aliases),
                    count=r['count'],
                )
                for r in parsed_rows
            ])

        messages.success(request, f'{len(parsed_rows)} row(s) read. Review and correct them below.')
        return redirect('estimator_project_import_review', pk=project.pk)

    return render(request, 'estimator/project_import_upload.html', {'project': project})


def project_import_review(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        row_ids = request.POST.getlist('import_row_id[]')
        module_type_ids = request.POST.getlist('module_type[]')
        zones = request.POST.getlist('zone[]')
        segment_ids = request.POST.getlist('segment[]')
        counts = request.POST.getlist('count[]')

        staged_by_id = {r.id: r for r in project.import_rows.all()}
        to_update = []
        for index, row_id_raw in enumerate(row_ids):
            row_id_raw = row_id_raw.strip()
            row = staged_by_id.get(int(row_id_raw)) if row_id_raw.isdigit() else None
            if not row:
                continue

            module_type_id = module_type_ids[index].strip() if index < len(module_type_ids) else ''
            segment_id = segment_ids[index].strip() if index < len(segment_ids) else ''
            count_raw = counts[index].strip() if index < len(counts) else ''
            try:
                count = int(count_raw)
            except ValueError:
                count = 0

            row.module_type_id = module_type_id or None
            row.segment_id = segment_id or None
            row.zone = zones[index].strip() if index < len(zones) else row.zone
            row.count = max(count, 0)
            to_update.append(row)

        ModuleImportRow.objects.bulk_update(to_update, ['module_type', 'segment', 'zone', 'count'])

        # Learned from whatever was just saved -- on *either* button, not only the
        # final "Confirm & Calculate". A multi-thousand-row sheet is realistically
        # corrected across many "Save Corrections" clicks long before every row is
        # valid, and a selection the user has saved is already a real decision worth
        # remembering, not something that should wait on the whole import finishing.
        # The browser already asked (via confirm()) whether to overwrite any mapping
        # that differs from what's saved -- this is just that answer. Missing/absent
        # means either nothing needed asking, or JS didn't run; either way, an
        # *existing* alias is left untouched rather than silently overwritten, though
        # a brand-new mapping is always learned regardless.
        update_existing_aliases = request.POST.get('update_aliases') == '1'
        fresh_rows = list(project.import_rows.select_related('module_type', 'segment').all())
        _learn_module_name_aliases(fresh_rows, update_existing_aliases)

        if action == 'confirm':
            invalid_rows = [r for r in fresh_rows if not r.is_valid]
            if invalid_rows:
                numbers = ', '.join(str(r.row_number) for r in invalid_rows)
                messages.error(
                    request,
                    f"Row(s) {numbers} still need a module type, segment, and/or count before this import can be "
                    f"confirmed -- corrections have been saved.",
                )
                return redirect('estimator_project_import_review', pk=project.pk)

            with transaction.atomic():
                next_order = (project.modules.aggregate(Max('order'))['order__max'] or -1) + 1
                ProjectModule.objects.bulk_create([
                    ProjectModule(
                        project=project,
                        segment=row.segment,
                        module_type=row.module_type,
                        count=row.count,
                        zone=row.zone,
                        order=next_order + i,
                    )
                    for i, row in enumerate(fresh_rows)
                ])
                project.import_rows.all().delete()

            messages.success(request, f'{len(fresh_rows)} module row(s) added from the import.')
            return redirect('estimator_project_builder', pk=project.pk)

        messages.success(request, 'Corrections saved.')
        return redirect('estimator_project_import_review', pk=project.pk)

    rows = list(project.import_rows.select_related('module_type', 'segment').all())
    normalized_names = {normalize_name(r.raw_module_name) for r in rows if r.raw_module_name}
    # Only the aliases relevant to raw names actually staged here -- lets the review
    # page's JS warn *before* submit when a correction would change an existing saved
    # mapping, without shipping the whole (potentially large) alias table.
    existing_aliases = ModuleNameAlias.objects.filter(raw_name_normalized__in=normalized_names).select_related('module_type')

    context = {
        'project': project,
        'rows': rows,
        'invalid_count': sum(1 for r in rows if not r.is_valid),
        'module_types': ModuleType.objects.order_by('name'),
        'segments': Segment.objects.order_by('name'),
        'aliases_json': safe_json({
            a.raw_name_normalized: {'module_type_id': a.module_type_id, 'module_type_name': a.module_type.name}
            for a in existing_aliases
        }),
    }
    return render(request, 'estimator/project_import_review.html', context)


def _learn_module_name_aliases(rows, update_existing):
    """Saves/updates ModuleNameAlias rows from a just-confirmed import: a raw name
    mapped to a ModuleType whose name it doesn't literally equal is a "learned"
    mapping worth remembering. A brand-new mapping is always saved; a mapping that
    already exists and differs is only overwritten when `update_existing` is True --
    the caller has already gotten the user's yes/no on that."""
    candidates = {}
    for row in rows:
        if not row.raw_module_name or not row.module_type_id:
            continue
        normalized = normalize_name(row.raw_module_name)
        if normalized == normalize_name(row.module_type.name):
            continue  # literal match -- always resolves the same way, nothing to remember
        candidates[normalized] = row  # last one wins if the same raw name repeats in this batch

    if not candidates:
        return

    existing_by_key = {
        a.raw_name_normalized: a
        for a in ModuleNameAlias.objects.filter(raw_name_normalized__in=candidates.keys())
    }

    to_create, to_update = [], []
    for normalized, row in candidates.items():
        existing = existing_by_key.get(normalized)
        if not existing:
            to_create.append(ModuleNameAlias(
                raw_name_normalized=normalized, raw_name=row.raw_module_name, module_type=row.module_type,
            ))
        elif existing.module_type_id != row.module_type_id and update_existing:
            existing.raw_name = row.raw_module_name
            existing.module_type = row.module_type
            to_update.append(existing)

    if to_create:
        ModuleNameAlias.objects.bulk_create(to_create)
    if to_update:
        ModuleNameAlias.objects.bulk_update(to_update, ['raw_name', 'module_type', 'updated_at'])


class ProjectReportView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = 'estimator/project_report.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['estimate'] = build_project_estimate(self.object)
        return context


def project_export_pdf(request, pk):
    project = get_object_or_404(Project, pk=pk)
    estimate = build_project_estimate(project)
    return render_project_report_pdf(estimate)


def project_export_excel(request, pk):
    project = get_object_or_404(Project, pk=pk)
    estimate = build_project_estimate(project)
    return render_project_report_excel(estimate)


@require_POST
def project_duplicate(request, pk):
    original = get_object_or_404(Project, pk=pk)
    with transaction.atomic():
        copy = Project.objects.create(
            name=unique_name(Project, f'{original.name} (Copy)'),
            customer=original.customer,
            complexity=original.complexity,
            notes=original.notes,
            minutes_per_working_day=original.minutes_per_working_day,
            created_by=request.user,
        )
        ProjectModule.objects.bulk_create([
            ProjectModule(
                project=copy,
                segment=pm.segment,
                module_type=pm.module_type,
                count=pm.count,
                zone=pm.zone,
                complexity_override=pm.complexity_override,
                order=pm.order,
            )
            for pm in original.modules.all()
        ])
    messages.success(request, f'Duplicated as "{copy.name}".')
    return redirect('estimator_project_builder', pk=copy.pk)


# --------------------------------------------------------------------------- Project Templates
#
# A shared team library: every is_estimator user (not just staff) can see and use every
# template, since these are reusable presets rather than personal data. A template is a
# standalone snapshot (its own ProjectTemplateModule rows) -- editing or deleting the
# Project it might have been saved from never touches it, and vice versa.

class ProjectTemplateListView(LoginRequiredMixin, ListView):
    model = ProjectTemplate
    template_name = 'estimator/template_list.html'
    context_object_name = 'templates'

    def get_queryset(self):
        return ProjectTemplate.objects.select_related('complexity', 'created_by')


class ProjectTemplateCreateView(LoginRequiredMixin, CreateView):
    model = ProjectTemplate
    form_class = ProjectTemplateForm
    template_name = 'estimator/add_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'New Template'
        context['cancel_url'] = reverse('estimator_template_list')
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Template "{form.instance.name}" created. Now add its modules below.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('estimator_template_builder', args=[self.object.pk])


class ProjectTemplateUpdateView(LoginRequiredMixin, UpdateView):
    model = ProjectTemplate
    form_class = ProjectTemplateForm
    template_name = 'estimator/add_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Template'
        context['cancel_url'] = reverse('estimator_template_builder', args=[self.object.pk])
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Template "{form.instance.name}" updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('estimator_template_builder', args=[self.object.pk])


class ProjectTemplateDeleteView(LoginRequiredMixin, DeleteView):
    model = ProjectTemplate
    template_name = 'estimator/confirm_delete.html'
    success_url = reverse_lazy('estimator_template_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        label = self.object.name
        self.object.delete()
        messages.success(request, f'Template "{label}" deleted.')
        return redirect(self.success_url)


class ProjectTemplateDetailView(LoginRequiredMixin, DetailView):
    """The Template Builder: the same module-rows editor as the Project Builder, minus
    the live matrix-based calculation -- a template is a reusable preset of module lines,
    not an estimate in its own right."""

    model = ProjectTemplate
    template_name = 'estimator/template_builder.html'
    context_object_name = 'template'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template = self.object

        segments = list(Segment.objects.order_by('name'))
        module_types = list(ModuleType.objects.order_by('name'))
        complexity_levels = list(ComplexityLevel.objects.order_by('display_order', 'multiplier'))

        context['rows'] = list(template.modules.select_related('segment', 'module_type', 'complexity_override').order_by('order', 'id'))
        context['segments_json'] = safe_json([{'id': s.id, 'name': s.name} for s in segments])
        context['module_types_json'] = safe_json([{'id': mt.id, 'name': mt.name} for mt in module_types])
        context['complexity_levels_json'] = safe_json([
            {'id': c.id, 'name': c.name, 'multiplier': float(c.multiplier)} for c in complexity_levels
        ])
        context['modules_json'] = safe_json([
            {
                'id': tm.id,
                'segment_id': tm.segment_id,
                'module_type_id': tm.module_type_id,
                'count': tm.count,
                'complexity_override_id': tm.complexity_override_id,
            }
            for tm in context['rows']
        ])
        return context


@require_POST
def template_modules_sync(request, pk):
    """Persists the Template Builder's module rows in one shot -- the template's
    counterpart to project_modules_sync(), same raw-POST-array convention."""

    template = get_object_or_404(ProjectTemplate, pk=pk)

    row_ids = request.POST.getlist('row_id[]')
    segment_ids = request.POST.getlist('segment[]')
    module_type_ids = request.POST.getlist('module_type[]')
    counts = request.POST.getlist('count[]')
    complexity_override_ids = request.POST.getlist('complexity_override[]')

    kept_ids = set()
    errors = []

    with transaction.atomic():
        for index, module_type_id in enumerate(module_type_ids):
            module_type_id = module_type_id.strip()
            if not module_type_id:
                continue

            segment_id = segment_ids[index].strip() if index < len(segment_ids) else ''
            if not segment_id:
                errors.append(f"Row {index + 1}: segment is required -- skipped.")
                continue

            count_raw = counts[index].strip() if index < len(counts) else ''
            try:
                # 0 is a valid template quantity -- a template mainly records which
                # module type/segment combinations go together; the actual count is
                # filled in per project. Only reject non-numeric or negative input.
                count = int(count_raw)
            except ValueError:
                errors.append(f"Row {index + 1}: count must be a whole number -- skipped.")
                continue
            if count < 0:
                errors.append(f"Row {index + 1}: count can't be negative -- skipped.")
                continue

            complexity_override_id = complexity_override_ids[index].strip() if index < len(complexity_override_ids) else ''
            row_id = row_ids[index].strip() if index < len(row_ids) else ''

            defaults = {
                'segment_id': segment_id,
                'module_type_id': module_type_id,
                'count': count,
                'complexity_override_id': complexity_override_id or None,
                'order': index,
            }

            if row_id:
                ProjectTemplateModule.objects.filter(pk=row_id, template=template).update(**defaults)
                kept_ids.add(int(row_id))
            else:
                tm = ProjectTemplateModule.objects.create(template=template, **defaults)
                kept_ids.add(tm.id)

        template.modules.exclude(id__in=kept_ids).delete()

    if errors:
        for e in errors:
            messages.error(request, e)
    else:
        messages.success(request, 'Template modules saved.')
    return redirect('estimator_template_builder', pk=template.pk)


class ProjectSaveAsTemplateView(LoginRequiredMixin, CreateView):
    """Snapshots a Project's current module rows into a brand-new ProjectTemplate, named
    by the user on this form. The template is fully independent afterward -- later
    changes to the project (or its deletion) never affect it."""

    model = ProjectTemplate
    form_class = SaveProjectAsTemplateForm
    template_name = 'estimator/add_form.html'

    def get_project(self):
        return get_object_or_404(Project, pk=self.kwargs['pk'])

    def get_initial(self):
        return {'name': unique_name(ProjectTemplate, f'{self.get_project().name} Template')}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Save "{self.get_project().name}" as Template'
        context['cancel_url'] = reverse('estimator_project_builder', args=[self.get_project().pk])
        return context

    def form_valid(self, form):
        project = self.get_project()
        form.instance.created_by = self.request.user
        form.instance.complexity = project.complexity
        form.instance.minutes_per_working_day = project.minutes_per_working_day
        with transaction.atomic():
            response = super().form_valid(form)
            ProjectTemplateModule.objects.bulk_create([
                ProjectTemplateModule(
                    template=self.object,
                    segment=pm.segment,
                    module_type=pm.module_type,
                    count=pm.count,
                    complexity_override=pm.complexity_override,
                    order=pm.order,
                )
                for pm in project.modules.all()
            ])
        messages.success(self.request, f'Saved "{project.name}" as template "{self.object.name}".')
        return response

    def get_success_url(self):
        return reverse('estimator_template_builder', args=[self.object.pk])
