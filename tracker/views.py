from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Project, Stage, StageHistory, trackerSegment, StageRemark, ProjectUpdate
from django.db.models import Q, F, Sum, Count
from django.utils import timezone
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
from collections import Counter
from collections import Counter, defaultdict 
from tracker.utils import (
    get_completion_percentage, get_otif_percentage, get_overall_status,
    get_schedule_status, get_next_milestone,get_final_project_otif

)
from django.core.cache import cache
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.pagesizes import letter, landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from django.http import HttpResponseRedirect, HttpResponse
import csv
from itertools import groupby
from operator import attrgetter

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('tracker_index')
    else:
        form = AuthenticationForm()
    return render(request, 'tracker/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('tracker_login')


def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "User registered successfully! Please log in.")
            return redirect('tracker_login')
    else:
        form = UserCreationForm()
    return render(request, 'tracker/signup.html', {'form': form})

@login_required
def index(request):
    projects = Project.objects.select_related('segment_con').all()
    return render(request, 'tracker/index.html', {'projects': projects})

@login_required
def new_project(request):
    if request.method == 'POST':
        code = request.POST['code']
        if Project.objects.filter(code=code).exists():
            messages.error(request, "Project code already exists.")
            return render(request, 'tracker/project_form.html', {'segments': trackerSegment.objects.all()})
        
        segment_id = request.POST.get('segment')
        segment_con = trackerSegment.objects.get(id=segment_id) if segment_id else None
        
        project = Project.objects.create(
            code=code, customer_name=request.POST['customer_name'],
            value=request.POST['value'], so_punch_date=parse_date(request.POST['so_punch_date']),
            segment_con=segment_con
        )
        
        # Create Automation Stages
        for stage_name, _ in Stage.AUTOMATION_STAGES:
            Stage.objects.create(project=project, name=stage_name, stage_type='Automation')
            
        # Create Emulation Stages
        for stage_name, _ in Stage.EMULATION_STAGES:
            Stage.objects.create(project=project, name=stage_name, stage_type='Emulation')

        messages.success(request, "Project created successfully!")
        return redirect('tracker_project_detail', project_id=project.id)
    
    return render(request, 'tracker/project_form.html', {'segments': trackerSegment.objects.all()})

@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project.objects.select_related('segment_con'), pk=project_id)

    if request.method == 'POST':
        stages_to_save = []
        active_tab = request.POST.get('active_tab', 'automation')
        
        # Determine which stages to process based on the button pressed
        if 'save_all_automation' in request.POST:
            stages_to_save = project.stages.filter(stage_type='Automation')
        elif 'save_all_emulation' in request.POST:
            stages_to_save = project.stages.filter(stage_type='Emulation')
        elif 'stage_id' in request.POST:
            stage_id = request.POST.get('stage_id')
            stages_to_save = project.stages.filter(id=stage_id)

        # --- NEW VALIDATION LOGIC ---
        validation_passed = True
        for stage in stages_to_save:
            new_status = request.POST.get(f'status_{stage.id}') or "Not started"
            actual_date_val = request.POST.get(f'actual_date_{stage.id}')
            
            # Check if status is 'Completed' but the date is missing
            if new_status == 'Completed' and not actual_date_val:
                messages.error(request, f"Please add a completion date for stage '{stage.name}' to save it as 'Completed'.")
                validation_passed = False
        
        # If any validation failed, stop and redirect back immediately
        if not validation_passed:
            base_url = reverse('tracker_project_detail', args=[project.id])
            redirect_url = f'{base_url}?active_tab={active_tab}'
            return HttpResponseRedirect(redirect_url)
        # --- END OF NEW VALIDATION LOGIC ---

        # If validation passed, proceed with saving changes
        success_message = "Changes saved successfully!" # Default message
        for stage in stages_to_save:
            new_planned = parse_date(request.POST.get(f'planned_date_{stage.id}'))
            new_status = request.POST.get(f'status_{stage.id}') or "Not started"
            actual_date_val = request.POST.get(f'actual_date_{stage.id}')
            new_actual = parse_date(actual_date_val) if new_status == 'Completed' and actual_date_val else None
            
            if stage.planned_date != new_planned:
                StageHistory.objects.create(stage=stage, changed_by=request.user, field_name="Planned Date", old_value=str(stage.planned_date), new_value=str(new_planned))
            if stage.status != new_status:
                StageHistory.objects.create(stage=stage, changed_by=request.user, field_name="Status", old_value=stage.status, new_value=new_status)
            if stage.actual_date != new_actual:
                StageHistory.objects.create(stage=stage, changed_by=request.user, field_name="Actual Date", old_value=str(stage.actual_date), new_value=str(new_actual))
            
            stage.planned_date = new_planned
            stage.status = new_status
            stage.actual_date = new_actual
            stage.save()

        # Update success message based on action
        if 'save_all_automation' in request.POST:
            success_message = "Automation Stages saved successfully!"
        elif 'save_all_emulation' in request.POST:
            success_message = "Emulation Stages saved successfully!"
        elif 'stage_id' in request.POST:
            stage_name = stages_to_save.first().name if stages_to_save else ''
            success_message = f"Stage '{stage_name}' updated successfully!"

        cache.delete(f'project_detail_{project_id}')
        messages.success(request, success_message)
        base_url = reverse('tracker_project_detail', args=[project.id])
        redirect_url = f'{base_url}?active_tab={active_tab}'
        return HttpResponseRedirect(redirect_url)

    # --- GET Request Logic ---
    # --- GET Request Logic (This part is unchanged) ---
    automation_stages_qs = Stage.objects.filter(project=project, stage_type='Automation').prefetch_related('remarks', 'history')
    emulation_stages_qs = Stage.objects.filter(project=project, stage_type='Emulation').prefetch_related('remarks', 'history')
    
    automation_order = {name: i for i, (name, _) in enumerate(Stage.AUTOMATION_STAGES)}
    emulation_order = {name: i for i, (name, _) in enumerate(Stage.EMULATION_STAGES)}
    automation_stages = sorted(list(automation_stages_qs), key=lambda s: automation_order.get(s.name, 99))
    emulation_stages = sorted(list(emulation_stages_qs), key=lambda s: emulation_order.get(s.name, 99))

    all_stages = automation_stages + emulation_stages
    
    updates = project.updates.select_related('author').all()[:5]
    updates_count = project.updates.count()
    
    recent_activity = StageHistory.objects.select_related('stage', 'changed_by').filter(stage__project=project).order_by('-changed_at')[:5]
    last_update_obj = StageHistory.objects.filter(stage__project=project).order_by('-changed_at').first()
    last_update_time = last_update_obj.changed_at if last_update_obj else project.so_punch_date
    
    # Timeline Calculation for Automation
    applicable_auto_stages = [s for s in automation_stages if s.status != "Not Applicable"]
    last_completed_auto_index = -1
    for i, stage in enumerate(applicable_auto_stages):
        if stage.status == "Completed": last_completed_auto_index = i
    timeline_progress_auto = 0
    total_auto_segments = len(applicable_auto_stages) - 1
    if last_completed_auto_index >= 0 and total_auto_segments > 0:
        timeline_progress_auto = round((last_completed_auto_index / total_auto_segments) * 100)

    # Timeline Calculation for Emulation
    applicable_emu_stages = [s for s in emulation_stages if s.status != "Not Applicable"]
    last_completed_emu_index = -1
    for i, stage in enumerate(applicable_emu_stages):
        if stage.status == "Completed": last_completed_emu_index = i
    timeline_progress_emu = 0
    total_emu_segments = len(applicable_emu_stages) - 1
    if last_completed_emu_index >= 0 and total_emu_segments > 0:
        timeline_progress_emu = round((last_completed_emu_index / total_emu_segments) * 100)

    # MODIFICATION: Get all remarks for each category for the new modals
    automation_remarks = StageRemark.objects.filter(
        stage__project=project, stage__stage_type='Automation'
    ).select_related('stage', 'added_by').order_by('-created_at')

    emulation_remarks = StageRemark.objects.filter(
        stage__project=project, stage__stage_type='Emulation'
    ).select_related('stage', 'added_by').order_by('-created_at')

    context = {
        'project': project, 
        'automation_stages': automation_stages, 
        'emulation_stages': emulation_stages,
        'updates': updates, 
        'updates_count': updates_count,
        'completion_percentage': get_completion_percentage(all_stages),
        'timeline_progress_auto': timeline_progress_auto,
        'timeline_progress_emu': timeline_progress_emu,
        'overall_otif_percentage': get_otif_percentage(all_stages),
        'project_otif': get_final_project_otif(all_stages),
        'overall_status': get_overall_status(all_stages),
        'automation_schedule_status': get_schedule_status(automation_stages), 
        'emulation_schedule_status': get_schedule_status(emulation_stages),
        'next_automation_milestone': get_next_milestone(automation_stages), 
        'next_emulation_milestone': get_next_milestone(emulation_stages),
        'last_update_time': last_update_time, 
        'recent_activity': recent_activity,
        # MODIFICATION: Add the new remark lists to the context
        'automation_remarks': automation_remarks,
        'emulation_remarks': emulation_remarks,

    }
    
    return render(request, 'tracker/project_detail.html', context)

@login_required
def delete_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    project.delete()
    messages.success(request, "Project deleted successfully.")
    return redirect('tracker_index')

@login_required
def edit_remark(request, remark_id):
    remark = get_object_or_404(StageRemark, pk=remark_id)
    project_id = remark.stage.project.id
    # Security check: only the author or a staff member can edit
    if request.user == remark.added_by or request.user.is_staff:
        if request.method == 'POST':
            new_text = request.POST.get('remark_text')
            if new_text:
                remark.text = new_text
                remark.save()
                messages.success(request, "Remark updated successfully.")
    else:
        messages.error(request, "You do not have permission to edit this remark.")
    return redirect('tracker_project_detail', project_id=project_id)

@login_required
def delete_remark(request, remark_id):
    remark = get_object_or_404(StageRemark, pk=remark_id)
    project_id = remark.stage.project.id
    # Security check: only the author or a staff member can delete
    if request.user == remark.added_by or request.user.is_staff:
        if request.method == 'POST':
            remark.delete()
            messages.success(request, "Remark deleted successfully.")
    else:
        messages.error(request, "You do not have permission to delete this remark.")
    return redirect('tracker_project_detail', project_id=project_id)

# In tracker/views.py

@login_required
def dashboard(request):
    today = timezone.now().date()
    period = request.GET.get('period', '30d')
    custom_start = request.GET.get('start_date_custom')
    custom_end = request.GET.get('end_date_custom')
    start_date, end_date = None, None
    display_period = "Custom"
    if custom_start and custom_end:
        start_date = parse_date(custom_start)
        end_date = parse_date(custom_end)
    else:
        period_map = {
            '7d': ("Last 7 Days", today - timedelta(days=7), today), '30d': ("Last 30 Days", today - timedelta(days=30), today),
            'this_month': ("Current Month", today.replace(day=1), today), 'this_year': ("Current Year", today.replace(day=1, month=1), today),
            'all': ("All Time", None, None),
        }
        display_period, start_date, end_date = period_map.get(period, ("Last 30 Days", today - timedelta(days=30), today))
    if period == 'all' and not (custom_start and custom_end):
        live_projects = Project.objects.all().distinct()
    else:
        completed_early_ids = Project.objects.filter(stages__name='Handover', stages__status='Completed', stages__actual_date__lt=start_date).values_list('id', flat=True)
        live_projects = Project.objects.filter(so_punch_date__lte=end_date).exclude(id__in=completed_early_ids).distinct()

    # --- CHRONIC PROJECTS LOGIC CORRECTION ---
    chronic_period = request.GET.get('chronic_period', '1y')
    chronic_cutoff_date = today
    if chronic_period == '6m': chronic_cutoff_date = today - relativedelta(months=6)
    elif chronic_period == '1y': chronic_cutoff_date = today - relativedelta(years=1)
    elif chronic_period == '2y': chronic_cutoff_date = today - relativedelta(years=2)

    # NEW, ROBUST QUERY
    # 1. First, get the IDs of all projects that are genuinely completed.
    completed_project_ids = Project.objects.filter(
        stages__name='Handover', 
        stages__status='Completed'
    ).values_list('id', flat=True)

    # 2. Then, find projects that are older than the cutoff AND are NOT in the completed list.
    chronic_projects = Project.objects.exclude(
        id__in=completed_project_ids
    ).filter(
        so_punch_date__lt=chronic_cutoff_date
    ).select_related('segment_con').order_by('so_punch_date')
    # --- END OF CORRECTION ---

    completed_stages = Stage.objects.filter(project__in=live_projects, status='Completed')
    if period != 'all' or (custom_start and custom_end):
        completed_stages = completed_stages.filter(actual_date__range=[start_date, end_date])
    total_completed_stages = completed_stages.count()
    on_time_stages = completed_stages.filter(actual_date__lte=F('planned_date')).count()
    department_otif = round((on_time_stages / total_completed_stages) * 100, 1) if total_completed_stages > 0 else 0
    total_live_projects = live_projects.count()
    active_live_projects = live_projects.filter(stages__status="In Progress").distinct().count()
    delayed_live_projects = live_projects.filter(stages__status="Hold").distinct().count()
    total_live_value = sum(p.value for p in live_projects)
    status_counts = Counter(p.get_overall_status() for p in live_projects)
    labels = [p.code for p in live_projects]
    on_track_data, at_risk_data, delayed_data = [], [], []
    for project in live_projects:
        completion = project.get_completion_percentage()
        if completion >= 80: on_track_data.append(completion); at_risk_data.append(0); delayed_data.append(0)
        elif completion >= 40: on_track_data.append(0); at_risk_data.append(completion); delayed_data.append(0)
        else: on_track_data.append(0); at_risk_data.append(0); delayed_data.append(completion)
    status_labels = list(status_counts.keys())
    status_data = list(status_counts.values())
    context = {
        'total_projects': total_live_projects, 'active_projects': active_live_projects, 'delayed_projects': delayed_live_projects, 'total_value': total_live_value,
        'department_otif': department_otif, 'recent_projects': Project.objects.all().order_by('-so_punch_date')[:5],
        'labels': labels, 'on_track_data': on_track_data, 'at_risk_data': at_risk_data, 'delayed_data': delayed_data,
        'status_labels': status_labels, 'status_data': status_data, 'selected_period_display': display_period,
        'custom_start_date': custom_start, 'custom_end_date': custom_end, 'chronic_projects': chronic_projects, 'selected_chronic_period': chronic_period,
    }
    return render(request, 'tracker/dashboard.html', context)

@login_required
def project_reports(request):
    projects_qs = Project.objects.select_related('segment_con').prefetch_related('stages').all()

    # --- Check for the 'hide_completed' filter ---
    hide_completed = request.GET.get('hide_completed') == '1'
    if hide_completed:
        # First, find the IDs of all projects that are considered "Completed"
        completed_project_ids = Project.objects.filter(
            stages__name='Handover',
            stages__status='Completed'
        ).values_list('id', flat=True)

        # Then, exclude them from our main query
        projects_qs = projects_qs.exclude(id__in=completed_project_ids)


    # --- Get standard filter values ---
    selected_segment_ids = request.GET.getlist('segments')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    min_value = request.GET.get('min_value')
    max_value = request.GET.get('max_value')

    if selected_segment_ids:
        projects_qs = projects_qs.filter(segment_con__id__in=selected_segment_ids)
    if start_date and end_date:
        projects_qs = projects_qs.filter(so_punch_date__range=[start_date, end_date])
    if min_value:
        try:
            projects_qs = projects_qs.filter(value__gte=float(min_value))
        except (ValueError, TypeError): pass
    if max_value:
        try:
            projects_qs = projects_qs.filter(value__lte=float(max_value))
        except (ValueError, TypeError): pass


    # --- Process Stage-Specific Filters ---
    stage_filters_from_request = {}
    for stage_key, stage_display in Stage.STAGE_NAMES:
        status = request.GET.get(f'stage_{stage_key}_status')
        start = request.GET.get(f'stage_{stage_key}_start')
        end = request.GET.get(f'stage_{stage_key}_end')

        
        if status or (start and end):
            stage_filters_from_request[stage_key] = {'status': status, 'start': start, 'end': end}
            stage_query_filters = {'stages__name': stage_key}
            if status: stage_query_filters['stages__status'] = status
            if start and end: stage_query_filters['stages__actual_date__range'] = [start, end]
            projects_qs = projects_qs.filter(**stage_query_filters)

    distinct_projects = projects_qs.distinct()

    # --- Prepare projects with their detailed summaries ---
    projects_with_details = []
    automation_order = {name: i for i, (name, _) in enumerate(Stage.AUTOMATION_STAGES)}
    emulation_order = {name: i for i, (name, _) in enumerate(Stage.EMULATION_STAGES)}

    for project in distinct_projects:
        all_stages = list(project.stages.all())

        auto_stages = sorted([s for s in all_stages if s.stage_type == 'Automation'], key=lambda s: automation_order.get(s.name, 99))
        emu_stages = sorted([s for s in all_stages if s.stage_type == 'Emulation'], key=lambda s: emulation_order.get(s.name, 99))

        projects_with_details.append({
            'project': project,
            'otif': project.get_otif_percentage(),
            'next_auto_milestone': get_next_milestone(auto_stages),
            'next_emu_milestone': get_next_milestone(emu_stages),
            'auto_schedule': get_schedule_status(auto_stages),
            'emu_schedule': get_schedule_status(emu_stages),
        })

    # --- Calculate Standard KPIs ---
    total_projects_found = distinct_projects.count()

    total_portfolio_value = distinct_projects.aggregate(total_value=Sum('value'))['total_value'] or 0
    completion_percentages = [p.get_completion_percentage() for p in distinct_projects]
    average_completion = sum(completion_percentages) / total_projects_found if total_projects_found > 0 else 0
    completed_stages = Stage.objects.filter(project__in=distinct_projects, status='Completed')
    total_completed = completed_stages.count()
    on_time_completed = completed_stages.filter(actual_date__lte=F('planned_date')).count()
    on_time_completion_rate = (on_time_completed / total_completed) * 100 if total_completed > 0 else 0

    
    
    # --- Prepare standard chart data ---
    status_counts = Counter(p.get_overall_status() for p in distinct_projects)
    status_labels = list(status_counts.keys())
    status_data = list(status_counts.values())
    segment_counts = distinct_projects.values('segment_con__name').annotate(count=Count('id')).order_by('-count')
    segment_labels = [item['segment_con__name'] for item in segment_counts if item['segment_con__name']]
    segment_data = [item['count'] for item in segment_counts if item['segment_con__name']]

    context = {

        'total_projects_found': total_projects_found,
        'total_portfolio_value': total_portfolio_value,
        'average_completion': average_completion,
        'all_segments': trackerSegment.objects.all(),
        'selected_segment_ids': [int(i) for i in selected_segment_ids],
        'start_date': start_date, 'end_date': end_date,
        'min_value': min_value, 'max_value': max_value,

        'status_labels': status_labels, 'status_data': status_data,
        'segment_labels': segment_labels, 'segment_data': segment_data,
        'stage_names': Stage.STAGE_NAMES, 'status_choices': Stage.STATUS_CHOICES,
        'stage_filters': stage_filters_from_request,
        'on_time_completion_rate': on_time_completion_rate,
        'hide_completed_active': hide_completed,

    }
    return render(request, 'tracker/project_report.html', context)

@login_required
def project_activity(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    history_logs = StageHistory.objects.filter(stage__project=project).order_by('-changed_at')
    return render(request, 'tracker/project_activity.html', {
        'project': project,
        'history_logs': history_logs,
    })


from itertools import groupby
from operator import attrgetter

@login_required
def upcoming_milestones(request):
    filter_type = request.GET.get('filter', 'all')
    today = timezone.now().date()
    
    # Use the existing helper function to get the initial filtered list of stages
    stages = get_filtered_stages(filter_type)
    
    # Add select_related for performance and order by project for grouping
    stages = stages.select_related('project').order_by('project__code', 'planned_date')

    # Group the stages by project
    stages_list = list(stages)
    grouped_stages = []
    for project, group in groupby(stages_list, key=attrgetter('project')):
        grouped_stages.append({
            'project': project,
            'stages': list(group)
        })

    return render(request, 'tracker/upcoming_milestones.html', {
        'grouped_stages': grouped_stages,
        'filter_type': filter_type,
        'filter_options': [
            ('All', 'all'), ('Overdue', 'overdue'), ('Today', 'today'),
            ('Tomorrow', 'tomorrow'), ('This Week', 'this_week'),
            ('Next Week', 'next_week'), ('This Month', 'this_month'),
            ('Next Month', 'next_month'),
        ],
        'today': today,
    })


def get_filtered_stages(filter_type):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    start_of_next_week = end_of_week + timedelta(days=1)
    end_of_next_week = start_of_next_week + timedelta(days=6)
    start_of_month = today.replace(day=1)
    start_of_next_month = (start_of_month + relativedelta(months=1)).replace(day=1)
    end_of_month = start_of_next_month - timedelta(days=1)
    end_of_next_month = (start_of_next_month + relativedelta(months=1)) - timedelta(days=1)

    date_ranges = {
        "today": (today, today),
        "tomorrow": (tomorrow, tomorrow),
        "this_week": (start_of_week, end_of_week),
        "next_week": (start_of_next_week, end_of_next_week),
        "this_month": (start_of_month, end_of_month),
        "next_month": (start_of_next_month, end_of_next_month),
    }

    if filter_type == 'overdue':
        return Stage.objects.filter(
            status__in=["Not started", "In Progress"],
            planned_date__lt=today
        ).order_by('planned_date')
    elif filter_type in date_ranges:
        start, end = date_ranges[filter_type]
        return Stage.objects.filter(
            status__in=["Not started", "In Progress"],
            planned_date__range=(start, end)
        ).order_by('planned_date')
    elif filter_type == 'all':
        return Stage.objects.exclude(status="Completed").order_by('planned_date')
    else:
        return Stage.objects.filter(
            status__in=["Not started", "In Progress"],
            planned_date__gte=today
        ).order_by('planned_date')
    
@login_required
def export_milestones_excel(request):
    filter_type = request.GET.get('filter', 'all').capitalize()
    stages = get_filtered_stages(filter_type)

    timestamp = datetime.now().strftime('%d-%m-%Y %H:%M')
    filename = f'Upcoming Milestones {filter_type} {timestamp}.csv'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Project Code', 'Customer', 'Milestone', 'Status', 'Planned Date'])

    for stage in stages:
        writer.writerow([
            stage.project.code,
            stage.project.customer_name,
            stage.name,
            stage.status,
            stage.planned_date
        ])
    return response

@login_required
def export_milestones_pdf(request):
    raw_filter = request.GET.get('filter', 'all')
    filter_type = raw_filter.lower()
    stages = get_filtered_stages(filter_type)

    # Format filename as "Upcoming Milestones [Filter] [dd-mm-yyyy HH-MM].pdf"
    timestamp = datetime.now().strftime('%d-%m-%Y %H:%M')
    filename = f'Upcoming Milestones {filter_type.capitalize()} {timestamp}.pdf'

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Upcoming Milestones - Filter: {filter_type.capitalize()}", styles['Heading2']))

    data = [['Project Code', 'Customer', 'Milestone', 'Status', 'Planned Date']]
    for stage in stages:
        data.append([
            stage.project.code,
            stage.project.customer_name,
            stage.name,
            stage.status,
            stage.planned_date.strftime('%Y-%m-%d') if stage.planned_date else 'N/A'
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_report_pdf(request):
    projects = Project.objects.select_related('segment_con').prefetch_related('stages').all()
    selected_segment_ids = request.GET.getlist('segments')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if selected_segment_ids:
        projects = projects.filter(segment_con__id__in=selected_segment_ids)
    if start_date and end_date:
        projects = projects.filter(so_punch_date__range=[start_date, end_date])

    for stage_key, stage_display in Stage.STAGE_NAMES:
        status = request.GET.get(f'stage_{stage_key}_status')
        start = request.GET.get(f'stage_{stage_key}_start')
        end = request.GET.get(f'stage_{stage_key}_end')
        if status or (start and end):
            stage_query_filters = {'stages__name': stage_key}
            if status:
                stage_query_filters['stages__status'] = status
            if start and end:
                stage_query_filters['stages__actual_date__range'] = [start, end]
            projects = projects.filter(**stage_query_filters)
    
    distinct_projects = projects.distinct()

    # --- Start Building the PDF ---
    response = HttpResponse(content_type='application/pdf')
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    filename = f"Project_Report_{timestamp}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Filtered Project Report", styles['Title']))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}", styles['Normal']))
    
    # Table Data
    table_data = [['Code', 'Customer', 'Segment', 'Value (INR)', 'Completion %', 'Status']]
    for p in distinct_projects:
        table_data.append([
            p.code,
            p.customer_name,
            p.segment_con.name if p.segment_con else 'N/A',
            f"{p.value:,.2f}",
            f"{p.get_completion_percentage()}%",
            p.get_overall_status()
        ])


    project_table = Table(table_data)
    project_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))


    elements.append(project_table)
    doc.build(elements)
    
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response

@login_required
def add_remark(request, stage_id):
    stage = get_object_or_404(Stage, id=stage_id)
    if request.method == 'POST':
        text = request.POST.get('remark')
        if text:
            StageRemark.objects.create(stage=stage, text=text, added_by=request.user)
            messages.success(request, "Remark added.")
    return redirect('tracker_project_detail', project_id=stage.project.id)

@login_required
def get_remarks(request, stage_id):
    stage = get_object_or_404(Stage, id=stage_id)
    return render(request, 'tracker/view_remarks_modal.html', {'stage': stage})

@login_required
def add_project_update(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if request.method == 'POST':
        text = request.POST.get('update_text')
        category = request.POST.get('update_category')
        needs_review = 'needs_review' in request.POST

        if text and category:
            ProjectUpdate.objects.create(
                project=project,
                author=request.user,
                text=text,
                category=category,
                needs_review=needs_review
            )
            messages.success(request, "Project update added successfully.")
        else:
            messages.error(request, "Update text and category are required.")
    
    # Redirect back to the project detail page
    return redirect('tracker_project_detail', project_id=project.id)

@login_required
def edit_project_update(request, update_id):
    update = get_object_or_404(ProjectUpdate, id=update_id, author=request.user)
    if request.method == 'POST':
        update.text = request.POST.get('update_text', update.text)
        update.category = request.POST.get('update_category', update.category)
        update.needs_review = 'needs_review' in request.POST
        
        # If the category is changed away from Risk, clear the mitigation plan
        if update.category != 'Risk':
            update.mitigation_plan = ''

        # If it is a risk, save the mitigation plan
        if update.category == 'Risk':
             update.mitigation_plan = request.POST.get('mitigation_plan', update.mitigation_plan)

        update.save()
        messages.success(request, "Update saved successfully.")
    return redirect('tracker_project_detail', project_id=update.project.id)

@login_required
def delete_project_update(request, update_id):
    update = get_object_or_404(ProjectUpdate, id=update_id, author=request.user)
    project_id = update.project.id
    update.delete()
    messages.success(request, "Update deleted.")
    return redirect('tracker_project_detail', project_id=project_id)

@login_required
def toggle_update_status(request, update_id):
    update = get_object_or_404(ProjectUpdate, id=update_id)
    if update.status == 'Open':
        update.status = 'Closed'
    else:
        update.status = 'Open'
    update.save()
    messages.success(request, f"'{update.category}' status changed to {update.status}.")
    return redirect('tracker_project_detail', project_id=update.project.id)



@login_required
def save_mitigation_plan(request, update_id):
    update = get_object_or_404(ProjectUpdate, id=update_id)
    if request.method == 'POST' and update.category == 'Risk':
        update.mitigation_plan = request.POST.get('mitigation_plan')
        update.save()
        messages.success(request, "Mitigation plan saved.")
    return redirect('tracker_project_detail', project_id=update.project.id)

@login_required
def all_project_updates(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    updates = project.updates.select_related('author').all()
    context = {
        'project': project,
        'updates': updates
    }
    return render(request, 'tracker/all_project_updates.html', context)

@login_required
def help_page(request):
    """
    Renders the help and documentation page.
    """
    return render(request, 'tracker/help_page.html')

