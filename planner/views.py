# planner/views.py

from django.shortcuts import render, redirect, get_object_or_404
from employees.models import Employee
from .models import (ProjectType, Segment, Category, Holiday,
                     Project, Activity, GeneralSettings, CapacitySettings,
                     SalesForecast, EffortBracket, Leave)
from datetime import date, timedelta, datetime
from collections import OrderedDict, defaultdict
from django.db.models import Min, Max
from .forms import ActivityForm, ProjectForm, LeaveForm
from django.urls import reverse
from urllib.parse import urlencode
from django.http import JsonResponse
import json
from .utils import calculate_end_date, count_working_days, calculate_effort_from_value, calculate_overlap_working_days
import calendar
from django.views.decorators.http import require_POST
from itertools import groupby

# Define this constant at the top of the file to avoid "magic numbers"
CR = 10_000_000

# --- Helper to shorten names ---
def _shorten_name(name):
    if not name: return name
    parts = name.strip().split()
    if len(parts) > 1:
        return f"{parts[0]} {parts[-1][0]}."
    return name

# --- Helper to prepare leaves map for Gantt ---
def _get_leaves_map():
    """
    Returns a dictionary mapping employee names to a list of ISO date strings
    representing their leave days.
    Structure: {'John Doe': ['2023-01-01', '2023-01-02'], ...}
    """
    leaves_qs = Leave.objects.select_related('employee').all()
    leaves_map = defaultdict(set) # Use set for faster lookup, convert to list for JSON
    
    for leave in leaves_qs:
        current = leave.start_date
        while current <= leave.end_date:
            leaves_map[leave.employee.name].add(current.isoformat())
            current += timedelta(days=1)
            
    # Convert sets to lists for JSON serialization
    return {k: list(v) for k, v in leaves_map.items()}

def _prepare_gantt_context(activities_qs):
    activities_list = list(activities_qs)
    today = date.today()
    
    # Shorten assignee names for display
    for activity in activities_list:
        if activity.assignee:
            activity.assignee.full_name = activity.assignee.name
            activity.assignee.name = _shorten_name(activity.assignee.name)
    
    holidays_map = {h.date: h.description for h in Holiday.objects.all()}

    min_start_dates = [a.start_date for a in activities_list if a.start_date]
    max_end_dates = [a.end_date for a in activities_list if a.end_date]
    gantt_start_date = min(min_start_dates) - timedelta(days=7) if min_start_dates else today - timedelta(days=7)
    gantt_end_date = max(max_end_dates) + timedelta(days=60) if max_end_dates else today + timedelta(days=60)
            
    gantt_data = {'start_date': gantt_start_date, 'end_date': gantt_end_date, 'months': OrderedDict()}
    header_dates = [gantt_start_date + timedelta(days=i) for i in range((gantt_end_date - gantt_start_date).days + 1)]
    for d in header_dates:
        month_year = d.strftime("%B %Y")
        gantt_data['months'][month_year] = gantt_data['months'].get(month_year, 0) + 1
    gantt_data['header_dates'] = header_dates
    
    return {
        'activities': activities_list,
        'gantt_data': gantt_data,
        'today': today,
        'holidays_map': holidays_map,
    }

def sales_forecast_view(request):
    if request.method == 'POST':
        if 'save_data' in request.POST:
            data = json.loads(request.POST.get('data', '[]'))
            SalesForecast.objects.all().delete()
            
            for item in data:
                opportunity_id = item.get('Opportunity', '')
                if not opportunity_id: 
                    continue
                    
                try:
                    amount_str = str(item.get('Total Amount (in Cr)', item.get('Total Amount', '0'))).replace(',', '')
                    total_amount = float(amount_str) * CR if amount_str else 0.0
                    prob_str = str(item.get('Probability(%)', '0')).replace('%', '')
                    probability = float(prob_str) if prob_str else 0.0
                    
                    start_date_val = None
                    end_date_val = None
                    
                    start_date_str = item.get('Start Date', '')
                    if start_date_str:
                        try:
                            start_date_val = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                start_date_val = datetime.strptime(start_date_str, '%d-%m-%Y').date()
                            except ValueError:
                                pass
                    
                    end_date_str = item.get('End date', '')
                    if end_date_str:
                        try:
                            end_date_val = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                end_date_val = datetime.strptime(end_date_str, '%d-%m-%Y').date()
                            except ValueError:
                                pass
                    
                    SalesForecast.objects.update_or_create(
                        opportunity=opportunity_id,
                        defaults={
                            'total_amount': total_amount,
                            'probability': probability,
                            'segment': item.get('Segment', ''),
                            'category': item.get('Category', ''),
                            'solution': item.get('Solution', ''),
                            'start_date': start_date_val,
                            'end_date': end_date_val
                        }
                    )
                except (ValueError, TypeError):
                    continue
                    
            return JsonResponse({'status': 'success'})
            
        if 'delete_all' in request.POST:
            SalesForecast.objects.all().delete()
            return redirect('planner_sales_forecast')

    project_types_with_brackets = ProjectType.objects.prefetch_related('effort_brackets')
    pt_bracket_map = {pt.id: list(pt.effort_brackets.all()) for pt in project_types_with_brackets}
    pt_map = {(pt.segment.name, pt.category.name): pt.id for pt in ProjectType.objects.select_related('segment', 'category')}
    
    forecast_data = list(SalesForecast.objects.all())
    total_forecasted_effort = 0
    for item in forecast_data:
        pt_id = pt_map.get((item.segment, item.category))
        brackets = pt_bracket_map.get(pt_id, [])
        item.calculated_effort = calculate_effort_from_value(item.total_amount, brackets)
        total_forecasted_effort += item.calculated_effort
        item.total_amount = item.total_amount / CR

    context = {
        'forecast_data': forecast_data, 
        'active_nav': 'sales_forecast',
        'total_forecasted_effort': total_forecasted_effort
    }
    return render(request, 'planner/sales_forecast.html', context)

def project_list_view(request):
    form = ProjectForm()
    if request.method == 'POST':
        project_id = request.POST.get('project_id_hidden')
        if project_id:
            instance = get_object_or_404(Project, pk=project_id)
            form = ProjectForm(request.POST, instance=instance)
        else:
            form = ProjectForm(request.POST)
            
        if form.is_valid():
            form.save()
            return redirect('planner_project_list')
    
    projects = Project.objects.select_related('segment', 'team_lead').prefetch_related('activities').all()
    
    segments = Segment.objects.filter(project__in=projects).distinct().order_by('name')
    team_leads = Employee.objects.filter(led_projects__in=projects).distinct().order_by('name')

    total_activities_count = Activity.objects.count()
    today = date.today()
    pending_activities_count = Activity.objects.filter(start_date__gt=today).count()
    active_projects_count = projects.filter(activities__isnull=False).distinct().count()
    
    context = {
        'form': form, 
        'projects': projects, 
        'active_nav': 'projects',
        'total_activities_count': total_activities_count,
        'pending_activities_count': pending_activities_count,
        'active_projects_count': active_projects_count,
        'segments': segments,
        'team_leads': team_leads,
    }
    return render(request, 'planner/project_list.html', context)

def consolidated_planner_view(request):
    form = ActivityForm()
    grouping_method = request.GET.get('group_by', 'project')
    sort_order = request.GET.get('sort', 'asc')

    if request.method == 'POST' and 'add_activity' in request.POST:
        form = ActivityForm(request.POST)
        if form.is_valid():
            form.save()
            query_params = {'group_by': grouping_method}
            if sort_order: query_params['sort'] = sort_order
            return redirect(f"{reverse('planner_consolidated_planner')}?{urlencode(query_params)}")

    all_activities_qs = Activity.objects.select_related('project__segment', 'project__team_lead', 'project_type__category', 'assignee').all()
    context = _prepare_gantt_context(all_activities_qs)

    # Fetch filter options
    all_projects = Project.objects.all()
    segments = Segment.objects.filter(project__in=all_projects).distinct().order_by('name')
    team_leads = Employee.objects.filter(led_projects__in=all_projects).distinct().order_by('name')
    
    assignees = Employee.objects.filter(is_active=True).order_by('name')

    display_data = defaultdict(list)
    if grouping_method == 'engineer':
        sorted_activities = sorted(context['activities'], key=lambda a: (a.assignee.name if a.assignee else "Unassigned", a.start_date))
        for act in sorted_activities:
            display_data[act.assignee.name if act.assignee else "Unassigned"].append(act)
            
    elif grouping_method == 'none':
        # Ungrouped mode with sorting
        reverse_sort = True if sort_order == 'desc' else False
        # Use a safe key for sorting: if start_date is None, use min or max date to avoid comparison errors
        sorted_activities = sorted(
            context['activities'], 
            key=lambda a: a.start_date if a.start_date else (date.max if reverse_sort else date.min), 
            reverse=reverse_sort
        )
        display_data['All Activities'] = sorted_activities
        
    else: 
        # Default fallback to 'project'
        grouping_method = 'project'
        activities_by_project = defaultdict(list)
        for act in context['activities']:
            activities_by_project[act.project_id].append(act)
        for project in Project.objects.order_by('project_id'):
            display_data[project.project_id] = sorted(activities_by_project.get(project.id, []), key=lambda a: a.start_date)

    gantt_init_data = {
        'activities': [
            {
                'pk': act.pk,
                'name': act.activity_name,
                'project': act.project.project_id,
                'assignee': getattr(act.assignee, 'full_name', act.assignee.name) if act.assignee else None,
                'start_date': act.start_date.isoformat() if act.start_date else None,
                'end_date': act.end_date.isoformat() if act.end_date else None,
            } for act in context['activities']
        ],
        'holidays': [h.isoformat() for h in context['holidays_map'].keys()],
        'leaves': _get_leaves_map(),  # NEW: Inject leaves
        'today': context['today'].isoformat()
    }

    context.update({
        'form': form,
        'active_nav': 'projects',
        'display_data': dict(display_data),
        'grouping_method': grouping_method,
        'sort_order': sort_order,
        'gantt_init_data': gantt_init_data,
        'segments': segments,
        'team_leads': team_leads,
        'assignees': assignees
    })
    return render(request, 'planner/activity_planner.html', context)

def activity_planner_view(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    form = ActivityForm(initial={'project': project})
    if request.method == 'POST' and 'add_activity' in request.POST:
        form = ActivityForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('planner_activity_planner', project_pk=project.pk)

    activities_qs = Activity.objects.filter(project=project).select_related(
        'project', 'project_type__category', 'assignee'
    ).order_by('start_date')

    context = _prepare_gantt_context(activities_qs)
    
    gantt_init_data = {
        'activities': [
            {
                'pk': act.pk,
                'name': act.activity_name,
                'project': act.project.project_id,
                'assignee': getattr(act.assignee, 'full_name', act.assignee.name) if act.assignee else None,
                'start_date': act.start_date.isoformat() if act.start_date else None,
                'end_date': act.end_date.isoformat() if act.end_date else None,
            } for act in context['activities']
        ],
        'holidays': [h.isoformat() for h in context['holidays_map'].keys()],
        'leaves': _get_leaves_map(),  # NEW: Inject leaves
        'today': context['today'].isoformat()
    }

    context.update({
        'project': project,
        'form': form,
        'active_nav': 'projects',
        'gantt_init_data': gantt_init_data
    })
    return render(request, 'planner/activity_planner.html', context)

# ... (rest of the views remain unchanged) ...
def _get_workforce_context():
    today = date.today()
    return {
        'workforce_counts': {
            'engineers': Employee.objects.filter(designation='ENGINEER', is_active=True).count(),
            'team_leads': Employee.objects.filter(designation='TEAM_LEAD', is_active=True).count(),
            'managers': Employee.objects.filter(designation='MANAGER', is_active=True).count(),
        },
        'all_employees': Employee.objects.all(),
        'designation_choices': Employee.DESIGNATION_CHOICES,
        'all_leaves': Leave.objects.filter(end_date__gte=today).select_related('employee').order_by('start_date'),
        'active_nav': 'workforce',
    }

def workforce_view(request):
    error_message = None
    entered_data = {}
    active_tab = request.GET.get('tab', 'employees')
    
    if request.method == 'POST':
        if 'add_employee' in request.POST:
            name = request.POST.get('name')
            designation = request.POST.get('designation')
            is_active_val = request.POST.get('is_active')
            is_active = True if is_active_val == 'True' else False
            
            if name and designation:
                if Employee.objects.filter(name__iexact=name).exists():
                    error_message = f"Team member with name '{name}' already exists."
                    entered_data = {'name': name, 'designation': designation, 'is_active': is_active_val}
                    active_tab = 'employees'
                else:
                    Employee.objects.create(name=name, designation=designation, is_active=is_active)
                    return redirect('planner_workforce')
        
        elif 'add_leave' in request.POST:
            leave_form = LeaveForm(request.POST)
            if leave_form.is_valid():
                leave_form.save()
                return redirect(f"{reverse('planner_workforce')}?tab=leaves")
            else:
                error_message = "Error adding leave. Please check dates."
                active_tab = 'leaves'

    context = _get_workforce_context()
    context.update({
        'error_message': error_message,
        'entered_data': entered_data,
        'leave_form': LeaveForm(),
        'active_tab': active_tab,
    })
    return render(request, 'planner/workforce.html', context)

def update_employee_view(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name')
        designation = request.POST.get('designation')
        is_active_val = request.POST.get('is_active')
        is_active = True if is_active_val == 'True' else False

        if name and designation:
            if Employee.objects.filter(name__iexact=name).exclude(pk=pk).exists():
                context = _get_workforce_context()
                context['error_message'] = f"Cannot update: Team member with name '{name}' already exists."
                return render(request, 'planner/workforce.html', context)
            
            employee.name = name
            employee.designation = designation
            employee.is_active = is_active
            employee.save()
            return redirect('planner_workforce')
    return redirect('planner_workforce')

def toggle_employee_status_view(request, pk):
    if request.method == 'POST':
        employee = get_object_or_404(Employee, pk=pk)
        employee.is_active = not employee.is_active
        employee.save()
        return redirect('planner_workforce')

def configuration_view(request):
    if request.method == 'POST':
        if 'add_holiday' in request.POST:
            Holiday.objects.get_or_create(date=request.POST.get('holiday_date'), defaults={'description': request.POST.get('description')})
            return redirect(f"{reverse('planner_configuration')}#holidays")
        elif 'add_project_type' in request.POST:
            segment = get_object_or_404(Segment, pk=request.POST.get('segment'))
            category = get_object_or_404(Category, pk=request.POST.get('category'))
            ProjectType.objects.get_or_create(segment=segment, category=category, defaults={
                'engineer_involvement': request.POST.get('engineer_involvement'),
                'team_lead_involvement': request.POST.get('team_lead_involvement'),
                'manager_involvement': request.POST.get('manager_involvement')
            })
            return redirect(f"{reverse('planner_configuration')}#project-types")
        elif 'update_general_settings' in request.POST:
            general_settings, _ = GeneralSettings.objects.get_or_create(pk=1)
            general_settings.working_hours_per_day = request.POST.get('working_hours_per_day', 8.0)
            general_settings.save()
            return redirect(f"{reverse('planner_configuration')}#general-settings")
        elif 'update_capacity_settings' in request.POST:
            for choice, _ in Employee.DESIGNATION_CHOICES:
                setting, _ = CapacitySettings.objects.get_or_create(designation=choice)
                setting.monthly_meeting_hours = request.POST.get(f'meeting_hours_{choice}', 0)
                setting.monthly_leave_hours = request.POST.get(f'leave_hours_{choice}', 0)
                setting.efficiency_loss_factor = request.POST.get(f'efficiency_{choice}', 0)
                setting.save()
            return redirect(f"{reverse('planner_configuration')}#capacity-settings")
        return redirect('planner_configuration')

    context = {
        'general_settings': GeneralSettings.objects.get_or_create(pk=1)[0],
        'capacity_settings': {c: CapacitySettings.objects.get_or_create(designation=c)[0] for c, _ in Employee.DESIGNATION_CHOICES},
        'all_segments': Segment.objects.all(), 'all_categories': Category.objects.all(),
        'project_types': ProjectType.objects.select_related('segment', 'category').all(),
        'holidays': Holiday.objects.all().order_by('date'), 'designations': Employee.DESIGNATION_CHOICES,
        'active_nav': 'configuration',
    }
    return render(request, 'planner/configuration.html', context)

def delete_project_view(request, pk):
    get_object_or_404(Project, pk=pk).delete()
    return redirect('planner_project_list')

def delete_employee_view(request, pk):
    get_object_or_404(Employee, pk=pk).delete()
    return redirect('planner_workforce')

def delete_leave_view(request, pk):
    get_object_or_404(Leave, pk=pk).delete()
    return redirect(f"{reverse('planner_workforce')}?tab=leaves")

def delete_holiday_view(request, pk):
    get_object_or_404(Holiday, pk=pk).delete()
    return redirect(f"{reverse('planner_configuration')}#holidays")

def edit_activity_view(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    next_url = request.GET.get('next')
    default_redirect_url = reverse('planner_activity_planner', kwargs={'project_pk': activity.project.pk})
    
    if request.method == 'POST':
        form = ActivityForm(request.POST, instance=activity)
        if form.is_valid():
            form.save()
            return redirect(next_url or default_redirect_url)
    else:
        form = ActivityForm(instance=activity)
        
    context = {
        'activity': activity, 
        'form': form, 
        'project': activity.project,
        'next_url': next_url or default_redirect_url
    }
    return render(request, 'planner/edit_activity.html', context)

def delete_activity_view(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    project_pk = activity.project.pk
    next_url = request.POST.get('next')
    activity.delete()
    default_redirect_url = reverse('planner_activity_planner', kwargs={'project_pk': project_pk})
    return redirect(next_url or default_redirect_url)

def edit_project_type_view(request, pk):
    project_type = get_object_or_404(ProjectType, pk=pk)
    next_url = request.GET.get('next')
    default_redirect_url = reverse('planner_configuration')
    
    if request.method == 'POST':
        project_type.segment = get_object_or_404(Segment, pk=request.POST.get('segment'))
        project_type.category = get_object_or_404(Category, pk=request.POST.get('category'))
        project_type.engineer_involvement = request.POST.get('engineer_involvement')
        project_type.team_lead_involvement = request.POST.get('team_lead_involvement')
        project_type.manager_involvement = request.POST.get('manager_involvement')
        project_type.save()
        
        next_url_from_post = request.POST.get('next')
        return redirect(next_url_from_post or default_redirect_url)
    
    context = {
        'type': project_type, 
        'all_segments': Segment.objects.all(), 
        'all_categories': Category.objects.all(),
        'next_url': next_url or default_redirect_url
    }
    return render(request, 'planner/edit_project_type.html', context)

def delete_project_type_view(request, pk):
    get_object_or_404(ProjectType, pk=pk).delete()
    return redirect(f"{reverse('planner_configuration')}#project-types")

def capacity_plan_view(request):
    view_type = request.GET.get('view_type', 'month')
    today = date.today()
    holidays = list(Holiday.objects.values_list('date', flat=True))
    general_settings, _ = GeneralSettings.objects.get_or_create(pk=1)
    capacity_settings = {c: CapacitySettings.objects.get_or_create(designation=c)[0] for c, _ in Employee.DESIGNATION_CHOICES}
    
    workforce_counts = {
        'ENGINEER': Employee.objects.filter(designation='ENGINEER', is_active=True).count(),
        'TEAM_LEAD': Employee.objects.filter(designation='TEAM_LEAD', is_active=True).count(),
        'MANAGER': Employee.objects.filter(designation='MANAGER', is_active=True).count()
    }
    
    periods = []
    if view_type == 'week':
        start_date = today - timedelta(days=today.weekday())
        for i in range(24): 
            p_start = start_date + timedelta(weeks=i)
            p_end = p_start + timedelta(days=6)
            periods.append({
                'start': p_start,
                'end': p_end,
                'key': p_start.strftime('%Y-W%W'),
                'label': p_start.strftime('W%W %d %b')
            })
    elif view_type == 'quarter':
        q_month = (today.month - 1) // 3 * 3 + 1
        start_date = date(today.year, q_month, 1)
        for i in range(8):
            year_offset = (start_date.month + (i*3) - 1) // 12
            month = (start_date.month + (i*3) - 1) % 12 + 1
            year = start_date.year + year_offset
            p_start = date(year, month, 1)
            
            if month >= 10:
                p_end = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                p_end = date(year, month + 3, 1) - timedelta(days=1)
            
            q_label = f"Q{(month-1)//3 + 1} {year}"
            periods.append({'start': p_start, 'end': p_end, 'key': q_label, 'label': q_label})
    else: 
        start_date = today.replace(day=1)
        for i in range(12):
            year_offset = (start_date.month + i - 1) // 12
            month = (start_date.month + i - 1) % 12 + 1
            year = start_date.year + year_offset
            p_start = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            p_end = date(year, month, last_day)
            periods.append({
                'start': p_start, 
                'end': p_end, 
                'key': p_start.strftime('%Y-%m'), 
                'label': p_start.strftime('%b %Y')
            })

    date_to_key = {}
    if periods:
        min_date = periods[0]['start']
        max_date = periods[-1]['end']
        curr = min_date
        while curr <= max_date:
            for p in periods:
                if p['start'] <= curr <= p['end']:
                    date_to_key[curr] = p['key']
                    break
            curr += timedelta(days=1)

    all_leaves = Leave.objects.select_related('employee').filter(end_date__gte=min_date, start_date__lte=max_date)
    leaves_by_designation = defaultdict(list)
    for leave in all_leaves:
        leaves_by_designation[leave.employee.designation].append(leave)

    supply_data = defaultdict(dict)
    for p in periods:
        working_days = count_working_days(p['start'], p['end'], holidays)
        period_days = (p['end'] - p['start']).days + 1
        month_factor = period_days / 30.44 

        for designation, count in workforce_counts.items():
            settings = capacity_settings[designation]
            
            total_leave_man_days = 0
            for leave in leaves_by_designation[designation]:
                total_leave_man_days += calculate_overlap_working_days(
                    leave.start_date, leave.end_date, 
                    p['start'], p['end'], holidays
                )
            
            gross_hours = ((count * working_days) - total_leave_man_days) * general_settings.working_hours_per_day
            non_project_hours = count * (settings.monthly_meeting_hours + settings.monthly_leave_hours) * month_factor
            efficiency_loss = (gross_hours - non_project_hours) * (settings.efficiency_loss_factor / 100)
            net_hours = gross_hours - non_project_hours - efficiency_loss
            
            supply_data[designation][p['key']] = {
                'available_hours': net_hours, 
                'headcount': count
            }

    # -- TRACK DAILY DEMAND FOR WEEKLY MAX CALCULATION --
    daily_demand = defaultdict(lambda: defaultdict(float)) # {designation: {date: hours}}
    
    live_workload_by_segment = defaultdict(lambda: defaultdict(float))
    forecasted_workload_by_segment = defaultdict(lambda: defaultdict(float))
    
    for activity in Activity.objects.select_related('assignee', 'project__segment').filter(
        assignee__isnull=False, start_date__isnull=False, end_date__isnull=False
    ):
        daily_hours = general_settings.working_hours_per_day
        current_date = activity.start_date
        while current_date <= activity.end_date:
            if current_date.weekday() < 5 and current_date not in holidays:
                # Track daily demand
                daily_demand[activity.assignee.designation][current_date] += daily_hours
                
                # Keep tracking sum for segment charts
                if current_date in date_to_key:
                    m_key = date_to_key[current_date]
                    if activity.project.segment:
                        live_workload_by_segment[activity.project.segment.name][m_key] += daily_hours
            current_date += timedelta(days=1)

    project_types_with_brackets = ProjectType.objects.prefetch_related('effort_brackets')
    pt_bracket_map = {pt.id: list(pt.effort_brackets.all()) for pt in project_types_with_brackets}
    pt_map = {(pt.segment.name, pt.category.name): pt.id for pt in ProjectType.objects.select_related('segment', 'category')}
    project_type_map = {pt.id: pt for pt in project_types_with_brackets}

    for forecast in SalesForecast.objects.filter(start_date__isnull=False, end_date__isnull=False):
        pt_id = pt_map.get((forecast.segment, forecast.category))
        if not pt_id: continue
        
        brackets = pt_bracket_map.get(pt_id, [])
        calculated_effort_days = calculate_effort_from_value(forecast.total_amount, brackets)
        if calculated_effort_days <= 0: continue
        
        total_window_days = count_working_days(forecast.start_date, forecast.end_date, holidays)
        if total_window_days <= 0: continue
        
        daily_effort_factor = calculated_effort_days / total_window_days
        p_type = project_type_map.get(pt_id)
        if not p_type: continue
        
        daily_eng_hours = general_settings.working_hours_per_day * (p_type.engineer_involvement / 100) * daily_effort_factor
        daily_tl_hours = general_settings.working_hours_per_day * (p_type.team_lead_involvement / 100) * daily_effort_factor
        daily_mgr_hours = general_settings.working_hours_per_day * (p_type.manager_involvement / 100) * daily_effort_factor
        
        total_daily_hours = daily_eng_hours + daily_tl_hours + daily_mgr_hours
        
        current_date = forecast.start_date
        while current_date <= forecast.end_date:
            if current_date.weekday() < 5 and current_date not in holidays:
                # Track daily demand
                daily_demand['ENGINEER'][current_date] += daily_eng_hours
                daily_demand['TEAM_LEAD'][current_date] += daily_tl_hours
                daily_demand['MANAGER'][current_date] += daily_mgr_hours

                # Keep tracking sum for segment charts
                if current_date in date_to_key:
                    month_key = date_to_key[current_date]
                    if forecast.segment:
                        forecasted_workload_by_segment[forecast.segment][month_key] += total_daily_hours
            current_date += timedelta(days=1)
    
    global_live_workload = defaultdict(float)
    global_forecast_workload = defaultdict(float)
    
    # Calculate global sums for Charts (Workload Volume)
    for activity in Activity.objects.filter(assignee__isnull=False, start_date__isnull=False, end_date__isnull=False):
        current_date = activity.start_date
        while current_date <= activity.end_date:
            if current_date.weekday() < 5 and current_date not in holidays:
                if current_date in date_to_key:
                    m_key = date_to_key[current_date]
                    global_live_workload[m_key] += general_settings.working_hours_per_day
            current_date += timedelta(days=1)
            
    for forecast in SalesForecast.objects.filter(start_date__isnull=False, end_date__isnull=False):
        pt_id = pt_map.get((forecast.segment, forecast.category))
        if not pt_id: continue
        brackets = pt_bracket_map.get(pt_id, [])
        calculated_effort_days = calculate_effort_from_value(forecast.total_amount, brackets)
        if calculated_effort_days <= 0: continue
        total_window_days = count_working_days(forecast.start_date, forecast.end_date, holidays)
        if total_window_days <= 0: continue
        daily_effort_factor = calculated_effort_days / total_window_days
        p_type = project_type_map.get(pt_id)
        if not p_type: continue
        
        total_daily_hours = general_settings.working_hours_per_day * daily_effort_factor * (
            (p_type.engineer_involvement + p_type.team_lead_involvement + p_type.manager_involvement) / 100
        )
        current_date = forecast.start_date
        while current_date <= forecast.end_date:
            if current_date.weekday() < 5 and current_date not in holidays:
                if current_date in date_to_key:
                    m_key = date_to_key[current_date]
                    global_forecast_workload[m_key] += total_daily_hours
            current_date += timedelta(days=1)

    chart_data = []
    for p in periods:
        live = global_live_workload.get(p['key'], 0)
        forecast = global_forecast_workload.get(p['key'], 0)
        chart_data.append({
            'month': p['label'], 
            'live_workload': round(live, 1),
            'forecasted_workload': round(forecast, 1),
            'total': round(live + forecast, 1)
        })
    
    segment_charts = []
    all_segments = Segment.objects.all().order_by('name')
    for segment in all_segments:
        seg_data = {'name': segment.name, 'data': []}
        for p in periods:
            live = live_workload_by_segment[segment.name].get(p['key'], 0)
            forecast = forecasted_workload_by_segment[segment.name].get(p['key'], 0)
            seg_data['data'].append({
                'month': p['label'],
                'live_workload': round(live, 1),
                'forecasted_workload': round(forecast, 1),
                'total': round(live + forecast, 1)
            })
        segment_charts.append(seg_data)

    report = []
    for des_value, des_display in Employee.DESIGNATION_CHOICES:
        des_data = {'designation': des_display, 'months': []}
        settings = capacity_settings[des_value]
        
        for p in periods:
            supply = supply_data[des_value].get(p['key'], {})
            available_hours = supply.get('available_hours', 0)
            headcount = supply.get('headcount', 0)
            
            # --- WEEKLY MAX REQUIREMENT LOGIC ---
            # 1. Identify all dates in this period
            dates_in_period = []
            curr = p['start']
            while curr <= p['end']:
                dates_in_period.append(curr)
                curr += timedelta(days=1)
            
            # 2. Group dates by ISO Week (Year, WeekNum)
            # This buckets days into their respective weeks.
            # groupby requires sorted input, but dates are already sorted.
            week_groups = groupby(dates_in_period, key=lambda d: d.isocalendar()[:2])
            
            weekly_headcount_reqs = []
            
            for week_key, days_iter in week_groups:
                days_in_week_chunk = list(days_iter)
                
                # Filter for working days only for capacity calc
                working_days_in_chunk = [d for d in days_in_week_chunk if d.weekday() < 5 and d not in holidays]
                count_working_days_week = len(working_days_in_chunk)
                
                if count_working_days_week == 0:
                    continue
                
                # Calculate Weekly Demand (Sum of daily demands for these days)
                weekly_demand = sum(daily_demand[des_value].get(d, 0.0) for d in days_in_week_chunk)
                
                # Calculate Effective Capacity Per Person for this week chunk
                # Formula: WorkingDays * HoursPerDay * EfficiencyFactor
                effective_weekly_capacity_per_person = (
                    count_working_days_week * general_settings.working_hours_per_day * (1 - settings.efficiency_loss_factor / 100)
                )
                
                # Calculate Headcount Req for this week
                if effective_weekly_capacity_per_person > 0:
                    req_hc = weekly_demand / effective_weekly_capacity_per_person
                    weekly_headcount_reqs.append(req_hc)
                else:
                    weekly_headcount_reqs.append(0)

            # 3. Determine Period Requirement (Max of Weekly Reqs)
            required_headcount = max(weekly_headcount_reqs) if weekly_headcount_reqs else 0.0
            
            # 4. Calculate Required Hours for Display
            # To make the table consistent, we back-calculate Required Hours 
            # based on the Max Headcount and the Period's average capacity per person.
            # This ensures (Available - Required) Variance reflects the headcount gap.
            
            period_avg_hours_per_person = (available_hours / headcount) if headcount > 0 else 0
            
            # Fallback if no headcount exists to determine period hours
            if period_avg_hours_per_person == 0:
                total_w_days = count_working_days(p['start'], p['end'], holidays)
                period_days = (p['end'] - p['start']).days + 1
                month_factor = period_days / 30.44
                gross = total_w_days * general_settings.working_hours_per_day
                deductions = (settings.monthly_meeting_hours + settings.monthly_leave_hours) * month_factor
                net = gross - deductions
                period_avg_hours_per_person = net * (1 - settings.efficiency_loss_factor / 100)
                
            required_hours = required_headcount * period_avg_hours_per_person

            des_data['months'].append({
                'month': p['label'], 
                'available_hours': available_hours, 
                'required_hours': required_hours, 
                'variance_hours': available_hours - required_hours, 
                'available_headcount': headcount, 
                'required_headcount': required_headcount
            })
        report.append(des_data)
    
    context = {
        'active_nav': 'capacity_plan', 
        'report_data': report,
        'chart_data': chart_data,
        'segment_charts': segment_charts,
        'view_type': view_type
    }
    return render(request, 'planner/capacity_plan.html', context)

def help_view(request):
    context = {'active_nav': 'help'}; return render(request, 'planner/help_page.html', context)

def get_effort_brackets_for_project_type(request, pk):
    project_type = get_object_or_404(ProjectType, pk=pk)
    brackets_data = []
    for bracket in project_type.effort_brackets.all():
        brackets_data.append({
            'id': bracket.id,
            'project_value': bracket.project_value / CR,
            'effort_days': bracket.effort_days
        })
    return JsonResponse({'brackets': brackets_data})

@require_POST
def add_effort_bracket_for_project_type(request, pk):
    project_type = get_object_or_404(ProjectType, pk=pk)
    data = json.loads(request.body)
    try:
        value_in_cr = float(data.get('project_value'))
        full_value = value_in_cr * CR
        
        bracket, created = EffortBracket.objects.update_or_create(
            project_type=project_type,
            project_value=full_value,
            defaults={'effort_days': int(data.get('effort_days'))}
        )
        response_data = {
            'status': 'success', 'id': bracket.id,
            'project_value': bracket.project_value / CR,
            'effort_days': bracket.effort_days, 'created': created
        }
        return JsonResponse(response_data)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@require_POST
def delete_effort_bracket_view(request, pk):
    get_object_or_404(EffortBracket, pk=pk).delete()
    return JsonResponse({'status': 'success'})