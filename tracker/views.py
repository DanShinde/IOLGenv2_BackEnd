from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from employees.models import Employee
from .models import Stage, StageHistory, trackerSegment, StageRemark, ProjectUpdate, UpdateRemark, Project, ContactPerson, ProjectComment

from django.db.models import Q, F, Sum, Count
from django.db.models.functions import TruncMonth
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
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.pagesizes import letter, landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

from django.http import HttpResponseRedirect, HttpResponse, JsonResponse, QueryDict
import csv
from itertools import groupby
from operator import attrgetter
import json
from django.contrib.auth import get_user_model
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side



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
            return render(request, 'tracker/project_form.html', {
                'segments': trackerSegment.objects.all(),
                'team_leads': Employee.objects.filter(designation='TEAM_LEAD')
                })

        segment_id = request.POST.get('segment')
        segment_con = trackerSegment.objects.get(id=segment_id) if segment_id else None

        # Get the Team Lead
        team_lead_id = request.POST.get('team_lead')
        team_lead = Employee.objects.get(id=team_lead_id) if team_lead_id else None

        project = Project.objects.create(
            code=code, customer_name=request.POST['customer_name'],
            value=request.POST['value'], so_punch_date=parse_date(request.POST['so_punch_date']),
            segment_con=segment_con,
            team_lead=team_lead
        )

        # ... stage creation logic is unchanged ...
        for stage_name, _ in Stage.AUTOMATION_STAGES:
            Stage.objects.create(project=project, name=stage_name, stage_type='Automation')
        for stage_name, _ in Stage.EMULATION_STAGES:
            Stage.objects.create(project=project, name=stage_name, stage_type='Emulation')

        messages.success(request, "Project created successfully!")
        return redirect('tracker_project_detail', project_id=project.id)

    # Pass team leads to context for the GET request
    context = {
        'segments': trackerSegment.objects.all(),
        'team_leads': Employee.objects.filter(designation='TEAM_LEAD')
    }
    return render(request, 'tracker/project_form.html', context)

@login_required
def edit_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == 'POST':
        # Update project fields from the form
        project.customer_name = request.POST['customer_name']
        project.value = request.POST['value']
        project.so_punch_date = parse_date(request.POST['so_punch_date'])

        segment_id = request.POST.get('segment')
        project.segment_con = trackerSegment.objects.get(id=segment_id) if segment_id else None

        team_lead_id = request.POST.get('team_lead')
        project.team_lead = Employee.objects.get(id=team_lead_id) if team_lead_id else None

        project.save()
        messages.success(request, f"Project '{project.code}' updated successfully!")
        return redirect('tracker_project_detail', project_id=project.id)

    # For a GET request, show the form pre-filled with project data
    context = {
        'project': project,
        'segments': trackerSegment.objects.all(),
        'team_leads': Employee.objects.filter(designation='TEAM_LEAD')
    }
    return render(request, 'tracker/project_form.html', context)

@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project.objects.select_related('segment_con'), pk=project_id)

    contact_persons = ContactPerson.objects.all()


    if request.method == 'POST':
        active_tab = request.POST.get('active_tab', 'automation')

        # --- Handle Note/Remark Addition First ---
        if 'add_project_comment' in request.POST:
            note_text = request.POST.get('note_text')
            
            if note_text:
                ProjectComment.objects.create(project=project, text=note_text, added_by=request.user)
                messages.success(request, "Note added successfully.")
            else:
                messages.error(request, "Please enter a note to save.")
            
            base_url = reverse('tracker_project_detail', args=[project.id])
            # Redirect with a hash to scroll to the notes section
            redirect_url = f'{base_url}?active_tab={active_tab}#project-notes'
            return HttpResponseRedirect(redirect_url)

        stages_to_save = []
        if 'save_all_automation' in request.POST:
            stages_to_save = project.stages.filter(stage_type='Automation')
        elif 'save_all_emulation' in request.POST:
            stages_to_save = project.stages.filter(stage_type='Emulation')
        elif 'stage_id' in request.POST:
            stage_id = request.POST.get('stage_id')
            stages_to_save = project.stages.filter(id=stage_id)

        validation_passed = True
        for stage in stages_to_save:
            new_status = request.POST.get(f'status_{stage.id}') or "Not started"
            actual_date_val = request.POST.get(f'actual_date_{stage.id}')
            
            if new_status == 'Completed' and not actual_date_val:
                messages.error(request, f"Please add an actual finish date for stage '{stage.name}' to save it as 'Completed'.")
                validation_passed = False
        
        if not validation_passed:
            base_url = reverse('tracker_project_detail', args=[project.id])
            redirect_url = f'{base_url}?active_tab={active_tab}'
            return HttpResponseRedirect(redirect_url)

        success_message = "Changes saved successfully!"
        for stage in stages_to_save:

            # Get new values from the form

            new_planned_start_str = request.POST.get(f'planned_start_date_{stage.id}')
            new_planned_str = request.POST.get(f'planned_date_{stage.id}')

            new_status = request.POST.get(f'status_{stage.id}') or "Not started"
            actual_date_val = request.POST.get(f'actual_date_{stage.id}')
            new_completion_percentage = request.POST.get(f'completion_percentage_{stage.id}')
            


            # Safely parse date strings

            new_planned_start = parse_date(new_planned_start_str) if new_planned_start_str else None
            new_planned = parse_date(new_planned_str) if new_planned_str else None
            new_actual = parse_date(actual_date_val) if new_status == 'Completed' and actual_date_val else None
            new_completion = int(new_completion_percentage) if new_completion_percentage else 0



            # Log changes to history

            if stage.planned_start_date != new_planned_start:
                StageHistory.objects.create(stage=stage, changed_by=request.user, field_name="Planned Start Date", old_value=str(stage.planned_start_date), new_value=str(new_planned_start))
            if stage.planned_date != new_planned:
                StageHistory.objects.create(stage=stage, changed_by=request.user, field_name="Planned Finish Date", old_value=str(stage.planned_date), new_value=str(new_planned))
            if stage.status != new_status:
                StageHistory.objects.create(stage=stage, changed_by=request.user, field_name="Status", old_value=stage.status, new_value=new_status)
            if stage.actual_date != new_actual:
                StageHistory.objects.create(stage=stage, changed_by=request.user, field_name="Actual Finish Date", old_value=str(stage.actual_date), new_value=str(new_actual))
            if stage.completion_percentage != new_completion:
                StageHistory.objects.create(stage=stage, changed_by=request.user, field_name="% Completion", old_value=str(stage.completion_percentage), new_value=str(new_completion))
            
            stage.planned_start_date = new_planned_start
            stage.planned_date = new_planned
            stage.status = new_status
            stage.actual_date = new_actual
            stage.completion_percentage = new_completion
            stage.save()

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

    # Filter stages based on status if provided
    status_filter = request.GET.get('status_filter')

    automation_stages_qs = Stage.objects.filter(project=project, stage_type='Automation').prefetch_related('remarks', 'history')
    emulation_stages_qs = Stage.objects.filter(project=project, stage_type='Emulation').prefetch_related('remarks', 'history')
    
    if status_filter:
        automation_stages_qs = automation_stages_qs.filter(status=status_filter)
        emulation_stages_qs = emulation_stages_qs.filter(status=status_filter)
    
    automation_order = {name: i for i, (name, _) in enumerate(Stage.AUTOMATION_STAGES)}
    emulation_order = {name: i for i, (name, _) in enumerate(Stage.EMULATION_STAGES)}
    automation_stages = sorted(list(automation_stages_qs), key=lambda s: automation_order.get(s.name, 99))
    emulation_stages = sorted(list(emulation_stages_qs), key=lambda s: emulation_order.get(s.name, 99))

    all_stages = automation_stages + emulation_stages
    
    updates = project.updates.select_related('author').prefetch_related('who_contact', 'remarks').all()[:5]
    updates_count = project.updates.count()
    
    recent_activity = StageHistory.objects.select_related('stage', 'changed_by').filter(stage__project=project).order_by('-changed_at')[:5]
    last_update_obj = StageHistory.objects.filter(stage__project=project).order_by('-changed_at').first()
    last_update_time = last_update_obj.changed_at if last_update_obj else project.so_punch_date
    
    applicable_auto_stages = [s for s in automation_stages if s.status != "Not Applicable"]
    last_completed_auto_index = -1
    for i, stage in enumerate(applicable_auto_stages):
        if stage.status == "Completed": last_completed_auto_index = i
    timeline_progress_auto = 0
    total_auto_segments = len(applicable_auto_stages) - 1
    if last_completed_auto_index >= 0 and total_auto_segments > 0:
        timeline_progress_auto = round((last_completed_auto_index / total_auto_segments) * 100)

    applicable_emu_stages = [s for s in emulation_stages if s.status != "Not Applicable"]
    last_completed_emu_index = -1
    for i, stage in enumerate(applicable_emu_stages):
        if stage.status == "Completed": last_completed_emu_index = i
    timeline_progress_emu = 0
    total_emu_segments = len(applicable_emu_stages) - 1
    if last_completed_emu_index >= 0 and total_emu_segments > 0:
        timeline_progress_emu = round((last_completed_emu_index / total_emu_segments) * 100)

    project_comments = project.comments.select_related('added_by').order_by('created_at')
    
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
        'project_comments': project_comments,

        'contact_persons': contact_persons,
        'status_choices': Stage.STATUS_CHOICES,
        'selected_status_filter': status_filter,

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
        display_period, start_date, end_date = period_map.get(period,("Last 30 Days", today - timedelta(days=30), today))
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

# tracker/views.py

@login_required
def project_reports(request):
    # --- Session logic for retaining filters ---
    
    # 1. Handle explicit reset action
    if 'reset' in request.GET:
        if 'report_filters' in request.session:
            del request.session['report_filters']
        return redirect('project_reports')

    # Determine which query parameters to use: from request or from session
    if not request.GET: # If no filters in URL
        # Check if filters are stored in session
        if 'report_filters' in request.session:
            # Rebuild query string and redirect
            saved_filters = request.session.get('report_filters', {})
            if saved_filters:
                query_dict = QueryDict(mutable=True)
                query_dict.update(saved_filters)
                return redirect(f"{reverse('project_reports')}?{query_dict.urlencode()}")
    else:
        # Filters are in the URL, save them to the session
        request.session['report_filters'] = request.GET.dict()

    # The rest of the view logic now uses the active query parameters
    query_params = request.GET or request.session.get('report_filters', {})
    
    # --- The FIX is in this line: We add select_related and prefetch_related ---
    projects_qs = Project.objects.select_related('segment_con', 'team_lead').prefetch_related('stages').all()

    # --- Get standard filter values ---
    # getlist needs a QueryDict, not a regular dict
    params_for_getlist = QueryDict(mutable=True)
    params_for_getlist.update(query_params)
    selected_segment_ids = params_for_getlist.getlist('segments')
    selected_team_lead_ids = params_for_getlist.getlist('team_leads')

    start_date = query_params.get('start_date')
    end_date = query_params.get('end_date')
    min_value = query_params.get('min_value')
    max_value = query_params.get('max_value')

    if selected_segment_ids:
        projects_qs = projects_qs.filter(segment_con__id__in=selected_segment_ids)

    if selected_team_lead_ids:
        projects_qs = projects_qs.filter(team_lead__id__in=selected_team_lead_ids)

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
        status = query_params.get(f'stage_{stage_key}_status')
        start = query_params.get(f'stage_{stage_key}_start')
        end = query_params.get(f'stage_{stage_key}_end')
        planned_start = query_params.get(f'stage_{stage_key}_planned_start')
        planned_end = query_params.get(f'stage_{stage_key}_planned_end')
        schedule_statuses = params_for_getlist.getlist(f'stage_{stage_key}_schedule_status')

        if status or (start and end) or (planned_start and planned_end) or schedule_statuses:
            stage_filters_from_request[stage_key] = {
                'status': status, 
                'start': start, 
                'end': end,
                'planned_start': planned_start,
                'planned_end': planned_end,
                'schedule_status': schedule_statuses
            }
            
            # Base filter for the specific stage name
            stage_q = Q(stages__name=stage_key)

            # Apply Schedule Logic (Planned vs Actual)
            if schedule_statuses:
                schedule_q = Q()
                if 'delayed' in schedule_statuses:
                    schedule_q |= Q(stages__actual_date__gt=F('stages__planned_date'))
                if 'on_time' in schedule_statuses:
                    schedule_q |= Q(stages__actual_date__lte=F('stages__planned_date'))
                if 'overdue' in schedule_statuses:
                    schedule_q |= Q(stages__status__in=['Not started', 'In Progress'], stages__planned_date__lt=timezone.now().date())
                stage_q &= schedule_q

            stage_query_filters = {}
            if status: stage_query_filters['stages__status'] = status
            if start and end: stage_query_filters['stages__actual_date__range'] = [start, end]
            if planned_start and planned_end: stage_query_filters['stages__planned_date__range'] = [planned_start, planned_end]
            
            # Combine Q object with standard kwargs
            projects_qs = projects_qs.filter(stage_q, **stage_query_filters)

    # --- Capture QS for Charts (Before Hide Completed) ---
    chart_projects_qs = projects_qs

    # --- Check for the 'hide_completed' filter ---
    hide_completed = query_params.get('hide_completed') == '1'
    if hide_completed:
        completed_project_ids = Project.objects.filter(
            stages__name='Handover',
            stages__status='Completed'
        ).values_list('id', flat=True)
        projects_qs = projects_qs.exclude(id__in=completed_project_ids)

    distinct_projects = projects_qs.distinct()
    distinct_chart_projects = chart_projects_qs.distinct()
    chart_project_ids = chart_projects_qs.values_list('id', flat=True).distinct()

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

    # --- NEW: Team Lead Distribution ---
    team_lead_counts = Counter(p.team_lead.name if p.team_lead else 'Unassigned' for p in distinct_projects)
    team_lead_labels = list(team_lead_counts.keys())
    team_lead_data = list(team_lead_counts.values())

    # --- NEW: Stage Bottleneck Analysis (Top Delayed Stages) ---
    # Count stages where Actual > Planned OR (Status is active AND Today > Planned)
    today = timezone.now().date()
    delayed_stages_qs = Stage.objects.filter(
        project__in=distinct_projects
    ).filter(
        Q(actual_date__gt=F('planned_date')) | 
        Q(status__in=['Not started', 'In Progress'], planned_date__lt=today)
    ).values('name').annotate(count=Count('id')).order_by('-count')
    
    stage_delay_labels = [item['name'] for item in delayed_stages_qs[:10]] # Top 10 bottlenecks
    stage_delay_data = [item['count'] for item in delayed_stages_qs[:10]]

    # --- NEW: Monthly Planned vs Actual Trends per Stage ---
    stage_trend_data = {}
    
    # Aggregate Planned Counts by Month
    planned_qs = Stage.objects.filter(
        project_id__in=chart_project_ids,
        planned_date__isnull=False
    ).annotate(
        month=TruncMonth('planned_date')
    ).values('name', 'month').annotate(count=Count('id')).order_by('month')

    # Aggregate Actual Counts by Month
    actual_qs = Stage.objects.filter(
        project_id__in=chart_project_ids,
        actual_date__isnull=False
    ).annotate(
        month=TruncMonth('actual_date')
    ).values('name', 'month').annotate(count=Count('id')).order_by('month')

    # Process into dictionary structure for Chart.js
    temp_trends = defaultdict(lambda: defaultdict(lambda: {'p': 0, 'a': 0}))

    for item in planned_qs:
        if item['month']:
            temp_trends[item['name']][item['month']]['p'] = item['count']
            
    for item in actual_qs:
        if item['month']:
            temp_trends[item['name']][item['month']]['a'] = item['count']
            
    for stage_name, month_data in temp_trends.items():
        sorted_months = sorted(month_data.keys())
        labels = [m.strftime('%b %Y') for m in sorted_months]
        years = [m.year for m in sorted_months]
        months = [m.month for m in sorted_months]
        
        financial_years = []
        for m in sorted_months:
            if m.month >= 4:
                fy_str = f"FY {str(m.year)[-2:]}-{str(m.year + 1)[-2:]}"
            else:
                fy_str = f"FY {str(m.year - 1)[-2:]}-{str(m.year)[-2:]}"
            financial_years.append(fy_str)

        p_data = [month_data[m]['p'] for m in sorted_months]
        a_data = [month_data[m]['a'] for m in sorted_months]
        
        stage_trend_data[stage_name] = {
            'labels': labels,
            'years': years,
            'financial_years': financial_years,
            'months': months,
            'planned': p_data,
            'actual': a_data
        }

    # --- NEW: OTIF Trends per Stage ---
    stage_otif_data = {}
    
    otif_qs = Stage.objects.filter(
        project_id__in=chart_project_ids,
        actual_date__isnull=False
    ).annotate(
        month=TruncMonth('actual_date')
    ).values('name', 'month').annotate(
        total=Count('id'),
        on_time=Count('id', filter=Q(planned_date__isnull=False) & Q(actual_date__lte=F('planned_date')))
    ).order_by('month')

    temp_otif = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'on_time': 0}))

    for item in otif_qs:
        if item['month']:
            temp_otif[item['name']][item['month']]['total'] = item['total']
            temp_otif[item['name']][item['month']]['on_time'] = item['on_time']

    for stage_name, month_data in temp_otif.items():
        sorted_months = sorted(month_data.keys())
        labels = [m.strftime('%b %Y') for m in sorted_months]
        years = [m.year for m in sorted_months]
        months = [m.month for m in sorted_months]
        
        financial_years = []
        for m in sorted_months:
            if m.month >= 4:
                fy_str = f"FY {str(m.year)[-2:]}-{str(m.year + 1)[-2:]}"
            else:
                fy_str = f"FY {str(m.year - 1)[-2:]}-{str(m.year)[-2:]}"
            financial_years.append(fy_str)

        total_data = [month_data[m]['total'] for m in sorted_months]
        on_time_data = [month_data[m]['on_time'] for m in sorted_months]
        
        stage_otif_data[stage_name] = {
            'labels': labels,
            'years': years,
            'financial_years': financial_years,
            'months': months,
            'total': total_data,
            'on_time': on_time_data
        }

    context = {

        'projects_with_details': projects_with_details,
        'total_projects_found': total_projects_found,
        'total_portfolio_value': total_portfolio_value,
        'average_completion': average_completion,
        'all_segments': trackerSegment.objects.all(),
        'all_team_leads': Employee.objects.filter(designation='TEAM_LEAD'),
        'selected_segment_ids': [int(i) for i in selected_segment_ids],
        'selected_team_lead_ids': [int(i) for i in selected_team_lead_ids],
        'start_date': start_date, 'end_date': end_date,
        'min_value': min_value, 'max_value': max_value,
        'status_labels': status_labels, 'status_data': status_data,
        'segment_labels': segment_labels, 'segment_data': segment_data,
        'team_lead_labels': team_lead_labels, 'team_lead_data': team_lead_data,
        'stage_delay_labels': stage_delay_labels, 'stage_delay_data': stage_delay_data,
        'stage_names': Stage.STAGE_NAMES, 'status_choices': Stage.STATUS_CHOICES,
        'automation_stage_names': Stage.AUTOMATION_STAGES,
        'emulation_stage_names': Stage.EMULATION_STAGES,
        'stage_filters': stage_filters_from_request,
        'on_time_completion_rate': on_time_completion_rate,
        'hide_completed_active': hide_completed,
        'stage_trend_data': json.dumps(stage_trend_data),
        'stage_otif_data': json.dumps(stage_otif_data),
    }
    return render(request, 'tracker/project_report.html', context)

@login_required
def project_activity(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    history_logs = StageHistory.objects.select_related('stage', 'changed_by').filter(stage__project=project).order_by('-changed_at')
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
        planned_start = request.GET.get(f'stage_{stage_key}_planned_start')
        planned_end = request.GET.get(f'stage_{stage_key}_planned_end')
        schedule_statuses = request.GET.getlist(f'stage_{stage_key}_schedule_status')

        if status or (start and end) or (planned_start and planned_end) or schedule_statuses:
            stage_q = Q(stages__name=stage_key)

            if schedule_statuses:
                schedule_q = Q()
                if 'delayed' in schedule_statuses:
                    schedule_q |= Q(stages__actual_date__gt=F('stages__planned_date'))
                if 'on_time' in schedule_statuses:
                    schedule_q |= Q(stages__actual_date__lte=F('stages__planned_date'))
                if 'overdue' in schedule_statuses:
                    schedule_q |= Q(stages__status__in=['Not started', 'In Progress'], stages__planned_date__lt=timezone.now().date())
                stage_q &= schedule_q

            stage_query_filters = {}
            if status:
                stage_query_filters['stages__status'] = status
            if start and end:
                stage_query_filters['stages__actual_date__range'] = [start, end]
            if planned_start and planned_end:
                stage_query_filters['stages__planned_date__range'] = [planned_start, planned_end]
            
            projects = projects.filter(stage_q, **stage_query_filters)
    
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
        push_pull_type = request.POST.get('push_pull_type')
        who_contact_ids = request.POST.getlist('who_contact')
        eta = parse_date(request.POST.get('eta_date')) if request.POST.get('eta_date') else None

        if text and push_pull_type:
            update = ProjectUpdate.objects.create(
                project=project,
                author=request.user,
                text=text,
                push_pull_type=push_pull_type,
                eta=eta,
                content_type='Project',
            )

            for contact_id in who_contact_ids:
                if contact_id:
                    try:
                        contact = ContactPerson.objects.get(pk=contact_id)
                        update.who_contact.add(contact)
                    except ContactPerson.DoesNotExist:
                        pass

            messages.success(request, "Push-Pull content added successfully.")
        else:
            messages.error(request, "Update text and type are required.")
    
    return redirect('tracker_project_detail', project_id=project.id)

@login_required
def add_general_update(request):
    if request.method == 'POST':
        text = request.POST.get('update_text')
        push_pull_type = request.POST.get('push_pull_type')
        who_contact_ids = request.POST.getlist('who_contact')

        eta = parse_date(request.POST.get('eta_date')) if request.POST.get('eta_date') else None

        if text and push_pull_type:
            update = ProjectUpdate.objects.create(
                author=request.user,
                text=text,
                push_pull_type=push_pull_type,
                eta=eta,
                content_type='General',
            )
            for contact_id in who_contact_ids:
                if contact_id:
                    try:
                        contact = ContactPerson.objects.get(pk=contact_id)
                        update.who_contact.add(contact)
                    except ContactPerson.DoesNotExist:
                        pass

            messages.success(request, "General content added successfully.")
        else:
            messages.error(request, "Update text and type are required.")

    return redirect('all_push_pull_content_filtered', filter='general')


@login_required
def edit_project_update(request, update_id):
    update = get_object_or_404(ProjectUpdate, id=update_id)
    if request.user == update.author or request.user.groups.filter(name='Trackers').exists():
        if request.method == 'POST':
            new_status = request.POST.get('update_status', update.status)
            
            if new_status == 'Closed' and update.status != 'Closed':
                update.closed_at = timezone.now()
            elif new_status != 'Closed' and update.status == 'Closed':
                update.closed_at = None
            
            # Update text and push_pull_type only if they're in the POST data
            if 'update_text' in request.POST:
                update.text = request.POST.get('update_text', update.text)
            if 'push_pull_type' in request.POST:
                update.push_pull_type = request.POST.get('push_pull_type', update.push_pull_type)
            
            update.status = new_status
            
            # Only update ETA if it's in the POST data
            if 'eta_date' in request.POST:
                eta_date = request.POST.get('eta_date')
                update.eta = parse_date(eta_date) if eta_date else None
            
            update.save()
            
            # Only update who_contact if it's in the POST data
            if 'who_contact' in request.POST:
                who_contact_ids = request.POST.getlist('who_contact')
                update.who_contact.clear()
                for contact_id in who_contact_ids:
                    if contact_id:
                        try:
                            contact = ContactPerson.objects.get(pk=contact_id)
                            update.who_contact.add(contact)
                        except ContactPerson.DoesNotExist:
                            pass

            messages.success(request, "Push-Pull content saved successfully.")
        
        referer = request.META.get('HTTP_REFERER')
        if referer and 'all-push-pull-content' in referer:
            filter_type = 'all'
            if 'filter=project' in referer:
                filter_type = 'project'
            elif 'filter=general' in referer:
                filter_type = 'general'
            return redirect('all_push_pull_content_filtered', filter=filter_type)
        if update.project:
            return redirect('tracker_project_detail', project_id=update.project.id)
        else:
            return redirect('all_push_pull_content_filtered', filter='general')
    else:
        messages.error(request, "You do not have permission to edit this update.")
        if update.project:
            return redirect('tracker_project_detail', project_id=update.project.id)
        else:
            return redirect('all_push_pull_content_filtered', filter='general')


@login_required
def delete_project_update(request, update_id):
    update = get_object_or_404(ProjectUpdate, id=update_id)
    if request.user == update.author or request.user.is_staff:
        project_id = update.project.id if update.project else None
        update.delete()
        messages.success(request, "Push-Pull content deleted.")
        referer = request.META.get('HTTP_REFERER')
        if referer and 'all-push-pull-content' in referer:
            filter_type = 'all'
            if 'filter=project' in referer:
                filter_type = 'project'
            elif 'filter=general' in referer:
                filter_type = 'general'
            return redirect('all_push_pull_content_filtered', filter=filter_type)
        
        if project_id:
            return redirect('tracker_project_detail', project_id=project_id)
        else:
            return redirect('all_push_pull_content')
    else:
        messages.error(request, "You do not have permission to delete this update.")
        if update.project:
            return redirect('tracker_project_detail', project_id=update.project.id)
        else:
            return redirect('all_push_pull_content')

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

    updates = project.updates.select_related('author').prefetch_related('who_contact', 'remarks').all()
    contact_persons = ContactPerson.objects.all()


    context = {
        'project': project,
        'updates': updates,
        'contact_persons': contact_persons,

    }
    return render(request, 'tracker/all_project_updates.html', context)


@login_required
def all_push_pull_content(request, filter=None):
    # Check for an explicit filter in the URL query parameters
    if 'filter' in request.GET and request.GET['filter'] in ['all', 'project', 'general']:
        if request.GET['filter'] == 'all':

            if 'push_pull_filter' in request.session:
                del request.session['push_pull_filter']
        else:
            request.session['push_pull_filter'] = request.GET['filter']

        # This redirect is crucial for a clean URL and consistent filtering
        return redirect('all_push_pull_content')

    # Get the current filters from the session and request
    current_filter = request.session.get('push_pull_filter', 'all')
    status_filter = request.GET.get('status_filter', 'all')
    push_pull_filter = request.GET.get('push_pull_filter', 'all') # ✅ NEW: Get push/pull filter


    updates_qs = ProjectUpdate.objects.select_related('author', 'project').prefetch_related('who_contact', 'remarks').order_by('-created_at')

    if current_filter == 'project':
        updates_qs = updates_qs.filter(content_type='Project')
    elif current_filter == 'general':
        updates_qs = updates_qs.filter(content_type='General')

    # ✅ NEW: Apply push/pull filtering
    if push_pull_filter == 'push':
        updates_qs = updates_qs.filter(push_pull_type='Push')
    elif push_pull_filter == 'pull':
        updates_qs = updates_qs.filter(push_pull_type='Pull')

    # Apply status filtering
    if status_filter == 'open':
        updates_qs = updates_qs.filter(status='Open')
    elif status_filter == 'closed':
        updates_qs = updates_qs.filter(status='Closed')

    updates = updates_qs.all()
    contact_persons = ContactPerson.objects.all()
    projects = Project.objects.all()

    context = {
        'updates': updates,
        'contact_persons': contact_persons,
        'projects': projects,
        'filter': current_filter,

        'status_filter': status_filter,
        'push_pull_filter': push_pull_filter, # ✅ NEW: Pass push/pull filter to template

    }
    return render(request, 'tracker/all_push_pull_content.html', context)

@login_required
def add_contact_person_ajax(request):
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        name = request.POST.get('name')
        if not name:
            return JsonResponse({'status': 'error', 'message': 'Name is required'}, status=400)
        
        contact, created = ContactPerson.objects.get_or_create(name=name)
        
        return JsonResponse({'status': 'success', 'id': contact.id, 'name': contact.name, 'created': created})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=405)


@login_required
def export_push_pull_excel(request):
    updates_qs = ProjectUpdate.objects.select_related('project', 'author').prefetch_related('who_contact', 'remarks')
    filter = request.GET.get('filter')

    if filter == 'project':
        updates_qs = updates_qs.filter(content_type='Project')
    elif filter == 'general':
        updates_qs = updates_qs.filter(content_type='General')

    updates = updates_qs.all()
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = f"all_push_pull_contents_{timezone.now().strftime('%Y-%m-%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename={filename}'

    
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "All Push-Pull Contents"
    
    # Headers
    headers = [
        'Project Code', 'Type', 'What', 'Who', 'ETA', 'Status', 'Created At', 'Closed At', 'Remarks'
    ]
    sheet.append(headers)
    
    # Populate with data
    for update in updates:
        # Join multiple contacts with a comma
        who_contacts_str = ", ".join([p.name for p in update.who_contact.all()])
        remarks_text = " | ".join([f"{r.added_by.username} ({r.created_at.strftime('%Y-%m-%d %H:%M')}): {r.text}" for r in update.remarks.all()])

        # --- FIX START ---
        # A date object does not have a tzinfo attribute, so it doesn't need to be replaced.
        # A datetime object does, and must be made naive to be compatible with openpyxl.
        created_at_naive = update.created_at.replace(tzinfo=None) if update.created_at else None
        closed_at_naive = update.closed_at.replace(tzinfo=None) if update.closed_at else None
        
        # The ETA field is a DateField, so no timezone removal is needed.
        eta_naive = update.eta
        # --- FIX END ---

        row = [
            update.project.code if update.project else 'N/A',
            update.get_push_pull_type_display(),
            update.text,
            who_contacts_str,
            eta_naive,
            update.status,
            created_at_naive,
            closed_at_naive,
            remarks_text
        ]
        sheet.append(row)

    workbook.save(response)
    
    return response

@login_required
def export_push_pull_pdf(request):

    updates_qs = ProjectUpdate.objects.select_related('project', 'author').prefetch_related('who_contact', 'remarks')
    filter = request.GET.get('filter')

    if filter == 'project':
        updates_qs = updates_qs.filter(content_type='Project')
    elif filter == 'general':
        updates_qs = updates_qs.filter(content_type='General')

    updates = updates_qs.all()

    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1*cm, rightMargin=1*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    elements = []
    styles = getSampleStyleSheet()

    long_text_style = ParagraphStyle(
        'long_text_style',
        parent=styles['Normal'],
        wordWrap='CJK',
        spaceAfter=6,
        alignment=4,
        textColor=colors.black,
        fontName='Helvetica',
    )
    
    header_style = ParagraphStyle(
        'header_style',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        textColor=colors.whitesmoke,
        alignment=1,
    )
    
    elements.append(Paragraph("All Push-Pull Contents", styles['Title']))
    elements.append(Paragraph(f"Report Generated on: {timezone.now().strftime('%d-%b-%Y %I:%M %p')}", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))

    table_data = [
        [
            Paragraph('Project Code', header_style),
            Paragraph('Type', header_style),
            Paragraph('What', header_style),
            Paragraph('Who', header_style),
            Paragraph('ETA', header_style),
            Paragraph('Status', header_style),
            Paragraph('Remarks', header_style)
        ]
    ]
    
    for update in updates:
        who_contacts_str = ", ".join([p.name for p in update.who_contact.all()])
        remarks_list = [f"• {r.added_by.username} ({r.created_at.strftime('%Y-%m-%d %H:%M')}): {r.text}" for r in update.remarks.all()]
        
        what_cell = Paragraph(update.text, long_text_style)
        who_cell = Paragraph(who_contacts_str if who_contacts_str else '-', long_text_style)
        remarks_cell = Paragraph("<br/>".join(remarks_list), long_text_style) if remarks_list else '-'
        
        row = [
            update.project.code if update.project else 'N/A',
            update.get_push_pull_type_display(),
            what_cell,
            who_cell,
            update.eta.strftime('%Y-%m-%d') if update.eta else '-',
            update.status,
            remarks_cell
        ]
        table_data.append(row)
        
    col_widths = [1.8*cm, 2.5*cm, 5*cm, 2*cm, 2.5*cm, 2.5*cm, 6.2*cm]
    
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('LEFTPADDING', (0, 0), (-1,-1), 6),
        ('RIGHTPADDING', (0, 0), (-1,-1), 6),
        ('WORDWRAP', (0, 0), (-1, -1), 1),
    ])

    table = Table(table_data, colWidths=col_widths)
    table.setStyle(table_style)
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f"all_push_pull_contents_{timezone.now().strftime('%Y-%m-%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename={filename}'
    
    return response


@login_required
def help_page(request):
    """
    Renders the help and documentation page.
    """
    return render(request, 'tracker/help_page.html')

@login_required
def update_stage_ajax(request, stage_id):
    if request.method == 'POST':
        stage = get_object_or_404(Stage, id=stage_id)
        
        try:
            data = json.loads(request.body)
            field_name = data.get('field_name')
            new_value = data.get('new_value')

            old_value = getattr(stage, field_name)

            # Map field names to user-friendly names for the history log
            field_map = {
                'planned_start_date': 'Planned Start Date',
                'planned_date': 'Planned Finish Date',
                'status': 'Status',
                'actual_date': 'Actual Finish Date',
                'completion_percentage': '% Completion',
            }
            history_field_name = field_map.get(field_name, field_name.replace('_', ' ').title())

            # Update the field on the stage object
            if 'date' in field_name:
                setattr(stage, field_name, parse_date(new_value) if new_value else None)
            else:
                setattr(stage, field_name, new_value)

            if field_name == 'status' and new_value != 'Completed':
                stage.actual_date = None
            
            stage.save()

            # Create a history record of the change
            StageHistory.objects.create(
                stage=stage,
                changed_by=request.user,
                field_name=history_field_name,
                old_value=str(old_value),
                new_value=str(new_value)
            )
            return JsonResponse({'status': 'success', 'message': 'Stage updated successfully.'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)



@login_required
def add_update_remark(request, update_id):
    update = get_object_or_404(ProjectUpdate, id=update_id)
    if request.method == 'POST':
        text = request.POST.get('remark_text')
        redirect_to = request.POST.get('redirect_to') # ✅ Get the new hidden field
        if text:
            remark = UpdateRemark.objects.create(
                update=update,
                text=text,
                added_by=request.user
            )
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'remark': {
                        'user': remark.added_by.username if remark.added_by else 'Unknown',
                        'date': remark.created_at.strftime("%b %d, %H:%M"),
                        'text': remark.text,
                        'initials': remark.added_by.username[:2].upper() if remark.added_by else '??'
                    }
                })

            messages.success(request, "Remark added successfully.")
            
    # ✅ Corrected redirect logic to handle both project and non-project updates
    if redirect_to == 'project_detail' and update.project:
        # Redirect back to the specific project detail page
        return redirect('tracker_project_detail', project_id=update.project.id)
    else:
        # Default to the general content page or the filtered page
        return redirect('all_push_pull_content_filtered', filter='general')

@login_required
def edit_update_remark(request, remark_id):
    remark = get_object_or_404(UpdateRemark, pk=remark_id)
    redirect_to = None

    if request.method == 'POST':
        # Grab the redirect_to value from the form first
        redirect_to = request.POST.get('redirect_to')
        new_text = request.POST.get('remark_text')

        # Security check: only the author or a staff member can edit
        if request.user == remark.added_by or request.user.is_staff:
            if new_text:
                remark.text = new_text
                remark.save()
                messages.success(request, "Remark updated successfully.")
        else:
            messages.error(request, "You do not have permission to edit this remark.")
    
    # ✅ Corrected redirect logic
    if redirect_to == 'project_detail' and remark.update.project:
        # Redirect back to the project page
        return redirect('tracker_project_detail', project_id=remark.update.project.id)
    else:
        # Default to the all push-pull content page
        return redirect('all_push_pull_content_filtered', filter='general')


@login_required
def delete_update_remark(request, remark_id):
    remark = get_object_or_404(UpdateRemark, pk=remark_id)
    redirect_to = request.POST.get('redirect_to')
    
    # Security check: only the author or a staff member can delete
    if request.user == remark.added_by or request.user.is_staff:
        if request.method == 'POST':
            remark.delete()
            messages.success(request, "Remark deleted successfully.")
    else:
        messages.error(request, "You do not have permission to delete this remark.")


    # ✅ Corrected redirect logic
    if redirect_to == 'project_detail' and remark.update.project:
        # Redirect back to the project page if the update has a project
        return redirect('tracker_project_detail', project_id=remark.update.project.id)
    else:
        # Redirect back to the general content page
        return redirect('all_push_pull_content_filtered', filter='general')
    

from uuid import UUID

def public_push_pull_content(request, access_token):
    try:
        # The access_token is ALREADY a UUID object because of the URL converter.
        valid_token = UUID("a1b2c3d4-e5f6-7890-1234-567890abcdef") 

        if access_token != valid_token:
            return HttpResponse("Unauthorized", status=401)
            
    except ValueError:
        return HttpResponse("Invalid Token", status=400)
    
    # ✅ NEW: Read filter parameters from the URL
    current_filter = request.GET.get('filter', 'all')
    status_filter = request.GET.get('status_filter', 'all')
    push_pull_filter = request.GET.get('push_pull_filter', 'all')

    updates_qs = ProjectUpdate.objects.select_related('author', 'project').prefetch_related('who_contact', 'remarks').order_by('-created_at')

    if current_filter == 'project':
        updates_qs = updates_qs.filter(content_type='Project')
    elif current_filter == 'general':
        updates_qs = updates_qs.filter(content_type='General')

    if push_pull_filter == 'push':
        updates_qs = updates_qs.filter(push_pull_type='Push')
    elif push_pull_filter == 'pull':
        updates_qs = updates_qs.filter(push_pull_type='Pull')
        
    if status_filter == 'open':
        updates_qs = updates_qs.filter(status='Open')
    elif status_filter == 'closed':
        updates_qs = updates_qs.filter(status='Closed')

    updates = updates_qs.all()
    contact_persons = ContactPerson.objects.all()

    # The redirect logic needs to be updated to redirect back to the public URL
    if request.method == 'POST':
        update_id = request.POST.get('update_id')
        update = get_object_or_404(ProjectUpdate, id=update_id)

        if 'update_status' in request.POST:
            update.status = request.POST['update_status']
            update.save()
            messages.success(request, f"Update status for item {update.id} changed to {update.status}.")
            return redirect('public_push_pull_content', access_token=str(access_token))
        
        if 'remark_text' in request.POST:
            text = request.POST.get('remark_text')
            if text:
                try:
                    public_user = get_user_model().objects.get(username='public_user')
                except get_user_model().DoesNotExist:
                    public_user = get_user_model().objects.create_user('public_user', 'public@example.com', 'some_random_password', is_active=False)

                UpdateRemark.objects.create(
                    update=update,
                    text=text,
                    added_by=public_user
                )
                messages.success(request, "Remark added successfully.")
            return redirect('public_push_pull_content', access_token=str(access_token))
    
    context = {
        'updates': updates,
        'contact_persons': contact_persons,
        'is_public_view': True,
        'access_token': str(access_token),
        'filter': current_filter,
        'status_filter': status_filter,
        'push_pull_filter': push_pull_filter,
    }
    return render(request, 'tracker/all_push_pull_content.html', context)


@login_required
def update_project_update_ajax(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            update_id = data.get('id')
            field = data.get('field')
            value = data.get('value')
            
            update = ProjectUpdate.objects.get(id=update_id)
            
            # Simple Authorization Check
            if request.user != update.author and not request.user.groups.filter(name='Trackers').exists() and not request.user.is_staff:
                 return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

            # Handle the specific fields
            if field == 'who_contact':
                # Expecting a list of IDs for Many-to-Many
                update.who_contact.set(value)
            elif field == 'eta':
                update.eta = parse_date(value) if value else None
            elif field == 'push_pull_type':
                update.push_pull_type = value
            elif field == 'status':
                update.status = value
                if value == 'Closed' and update.closed_at is None:
                    update.closed_at = timezone.now()
                elif value != 'Closed':
                    update.closed_at = None
            elif field == 'text':
                update.text = value
            
            update.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Bad Request'}, status=400)