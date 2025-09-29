# planner/views.py

from django.shortcuts import render, redirect, get_object_or_404
from .models import (Employee, ProjectType, Segment, Category, Holiday, 
                     Project, Activity, GeneralSettings, CapacitySettings, 
                     SalesForecast, EffortBracket)
from datetime import date, timedelta, datetime
from collections import OrderedDict, defaultdict
from django.db.models import Min, Max
from .forms import ActivityForm, ProjectForm
from django.urls import reverse
from urllib.parse import urlencode
from django.http import JsonResponse
import json
from .utils import calculate_end_date, count_working_days, calculate_effort_from_value
import calendar
from django.views.decorators.http import require_POST

# Define this constant at the top of the file to avoid "magic numbers"
CR = 10_000_000

# NEW: Helper function to handle common Gantt chart logic
def _prepare_gantt_context(activities_qs):
    """
    Takes a queryset of activities and returns a context dictionary 
    with all the necessary data for rendering a Gantt chart.
    """
    activities_list = list(activities_qs)
    today = date.today()
    
    holidays_map = {h.date: h.description for h in Holiday.objects.all()}
    holidays_set = set(holidays_map.keys())

    # 1. Calculate work_days for each activity
    for activity in activities_list:
        activity.work_days = set()
        if activity.start_date and activity.end_date:
            current_date = activity.start_date
            while current_date <= activity.end_date:
                if current_date.weekday() < 5 and current_date not in holidays_set:
                    activity.work_days.add(current_date)
                current_date += timedelta(days=1)
    
    # 2. Calculate assignee overlaps
    overlap_days = defaultdict(set)
    daily_occupancy = defaultdict(set)
    for activity in activities_list:
        if activity.assignee:
            for day in activity.work_days:
                if activity.assignee.name in daily_occupancy[day]:
                    overlap_days[day].add(activity.assignee.name)
                else:
                    daily_occupancy[day].add(activity.assignee.name)

    # 3. Determine the date range for the Gantt chart
    min_start_dates = [a.start_date for a in activities_list if a.start_date]
    max_end_dates = [a.end_date for a in activities_list if a.end_date]
    gantt_start_date = min(min_start_dates) - timedelta(days=7) if min_start_dates else today - timedelta(days=7)
    gantt_end_date = max(max_end_dates) + timedelta(days=60) if max_end_dates else today + timedelta(days=60)
            
    # 4. Build the gantt_data dictionary
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
        'overlap_days': overlap_days,
        'holidays_map': holidays_map,
    }

def sales_forecast_view(request):
    if request.method == 'POST':
        if 'save_data' in request.POST:
            data = json.loads(request.POST.get('data', '[]'))
            SalesForecast.objects.all().delete()  # Clear existing data first
            
            for item in data:
                opportunity_id = item.get('Opportunity', '')
                if not opportunity_id: 
                    continue
                    
                try:
                    # Handle the Total Amount - check both possible keys
                    amount_str = str(item.get('Total Amount (in Cr)', item.get('Total Amount', '0'))).replace(',', '')
                    total_amount = float(amount_str) * CR if amount_str else 0.0
                    
                    # Handle probability
                    prob_str = str(item.get('Probability(%)', '0')).replace('%', '')
                    probability = float(prob_str) if prob_str else 0.0
                    
                    # Handle dates - support both Y-m-d and d-m-Y formats
                    start_date_val = None
                    end_date_val = None
                    
                    start_date_str = item.get('Start Date', '')
                    if start_date_str:
                        try:
                            # Try Y-m-d format first
                            start_date_val = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                # Try d-m-Y format
                                start_date_val = datetime.strptime(start_date_str, '%d-%m-%Y').date()
                            except ValueError:
                                print(f"Could not parse start date: {start_date_str}")
                    
                    end_date_str = item.get('End date', '')
                    if end_date_str:
                        try:
                            # Try Y-m-d format first
                            end_date_val = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                # Try d-m-Y format
                                end_date_val = datetime.strptime(end_date_str, '%d-%m-%Y').date()
                            except ValueError:
                                print(f"Could not parse end date: {end_date_str}")
                    
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
                except (ValueError, TypeError) as e:
                    print(f"Could not process row for {opportunity_id}: {e}")
                    continue
                    
            return JsonResponse({'status': 'success'})
            
        if 'delete_all' in request.POST:
            SalesForecast.objects.all().delete()
            return redirect('sales_forecast')

    # Calculate effort for display
    project_types_with_brackets = ProjectType.objects.prefetch_related('effort_brackets')
    pt_bracket_map = {pt.id: list(pt.effort_brackets.all()) for pt in project_types_with_brackets}
    pt_map = {(pt.segment.name, pt.category.name): pt.id for pt in ProjectType.objects.select_related('segment', 'category')}
    
    forecast_data = list(SalesForecast.objects.all())
    for item in forecast_data:
        pt_id = pt_map.get((item.segment, item.category))
        brackets = pt_bracket_map.get(pt_id, [])
        item.calculated_effort = calculate_effort_from_value(item.total_amount, brackets)
        # Divide by conversion factor for display in Cr
        item.total_amount = item.total_amount / CR

    context = {'forecast_data': forecast_data, 'active_nav': 'sales_forecast'}
    return render(request, 'planner/sales_forecast.html', context)

def project_list_view(request):
    form = ProjectForm()
    if request.method == 'POST':
        project_id = request.POST.get('project_id_hidden')
        
        # If a project ID is present, we are editing an existing project.
        if project_id:
            instance = get_object_or_404(Project, pk=project_id)
            form = ProjectForm(request.POST, instance=instance)
        # Otherwise, we are creating a new project.
        else:
            form = ProjectForm(request.POST)
            
        if form.is_valid():
            form.save()
            return redirect('planner_project_list')
        # If form is not valid, the view will re-render with the form object
        # containing the errors, which you can display in your template.
    
    projects = Project.objects.select_related('segment').prefetch_related('activities').all()
    
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
    }
    return render(request, 'planner/project_list.html', context)


# MODIFIED: This view is now much cleaner
def consolidated_planner_view(request):
    form = ActivityForm()
    grouping_method = request.GET.get('group_by', 'project')
    if request.method == 'POST' and 'add_activity' in request.POST:
        form = ActivityForm(request.POST)
        if form.is_valid():
            form.save()
            query_string = urlencode({'group_by': grouping_method})
            return redirect(f"{reverse('consolidated_planner')}?{query_string}")

    # Start with the base queryset
    all_activities_qs = Activity.objects.select_related('project', 'project_type__category', 'assignee').all()
    
    # Prepare the common context data using our new helper function
    context = _prepare_gantt_context(all_activities_qs)

    # Grouping logic remains specific to this view
    display_data = defaultdict(list)
    if grouping_method == 'engineer':
        # Use the processed list from the context
        sorted_activities = sorted(context['activities'], key=lambda a: (a.assignee.name if a.assignee else "Unassigned", a.start_date))
        for act in sorted_activities:
            display_data[act.assignee.name if act.assignee else "Unassigned"].append(act)
    else: 
        grouping_method = 'project'
        activities_by_project = defaultdict(list)
        # Use the processed list from the context
        for act in context['activities']:
            activities_by_project[act.project_id].append(act)
        for project in Project.objects.order_by('project_id'):
            display_data[project.project_id] = sorted(activities_by_project.get(project.id, []), key=lambda a: a.start_date)

    # This logic is for the small bar chart next to the group name
    group_gantt_data = {}
    for group_name, activities_in_group in display_data.items():
        daily_activity_count = defaultdict(int)
        for activity in activities_in_group:
            for day in activity.work_days: daily_activity_count[day] += 1
        group_gantt_data[group_name] = {day: 2 if count > 1 else 1 for day, count in daily_activity_count.items()}
    
    # Update context with view-specific data
    context.update({
        'form': form,
        'active_nav': 'projects',
        'display_data': dict(display_data),
        'grouping_method': grouping_method,
        'group_gantt_data': group_gantt_data,
    })
    return render(request, 'planner/activity_planner.html', context)

# MODIFIED: This view is also much cleaner now
def activity_planner_view(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    form = ActivityForm(initial={'project': project})
    if request.method == 'POST' and 'add_activity' in request.POST:
        form = ActivityForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('activity_planner', project_pk=project.pk)

    # Get the activities for this specific project
    activities_qs = Activity.objects.filter(project=project).select_related(
        'project', 'project_type__category', 'assignee'
    ).order_by('start_date')

    # Use the same helper function to get all the Gantt data
    context = _prepare_gantt_context(activities_qs)
    
    # Update context with view-specific data
    context.update({
        'project': project,
        'form': form,
        'active_nav': 'projects',
    })
    return render(request, 'planner/activity_planner.html', context)

def workforce_view(request):
    if request.method == 'POST' and 'add_employee' in request.POST:
        name = request.POST.get('name')
        designation = request.POST.get('designation')
        if name and designation:
            Employee.objects.create(name=name, designation=designation)
        return redirect('workforce')
    context = {
        'workforce_counts': {
            'engineers': Employee.objects.filter(designation='ENGINEER').count(),
            'team_leads': Employee.objects.filter(designation='TEAM_LEAD').count(),
            'managers': Employee.objects.filter(designation='MANAGER').count(),
        },
        'all_employees': Employee.objects.all(),
        'designation_choices': Employee.DESIGNATION_CHOICES,
        'active_nav': 'workforce',
    }
    return render(request, 'planner/workforce.html', context)

def configuration_view(request):
    if request.method == 'POST':
        if 'add_holiday' in request.POST:
            Holiday.objects.get_or_create(date=request.POST.get('holiday_date'), defaults={'description': request.POST.get('description')})
        elif 'add_project_type' in request.POST:
            segment = get_object_or_404(Segment, pk=request.POST.get('segment'))
            category = get_object_or_404(Category, pk=request.POST.get('category'))
            ProjectType.objects.get_or_create(segment=segment, category=category, defaults={
                'engineer_involvement': request.POST.get('engineer_involvement'),
                'team_lead_involvement': request.POST.get('team_lead_involvement'),
                'manager_involvement': request.POST.get('manager_involvement')
            })
        elif 'update_general_settings' in request.POST:
            general_settings, _ = GeneralSettings.objects.get_or_create(pk=1)
            general_settings.working_hours_per_day = request.POST.get('working_hours_per_day', 8.0)
            general_settings.save()
            for choice, _ in Employee.DESIGNATION_CHOICES:
                setting, _ = CapacitySettings.objects.get_or_create(designation=choice)
                setting.monthly_meeting_hours = request.POST.get(f'meeting_hours_{choice}', 0)
                setting.monthly_leave_hours = request.POST.get(f'leave_hours_{choice}', 0)
                setting.efficiency_loss_factor = request.POST.get(f'efficiency_{choice}', 0)
                setting.save()
        return redirect('configuration')

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
    return redirect('workforce')

def delete_holiday_view(request, pk):
    get_object_or_404(Holiday, pk=pk).delete()
    return redirect('configuration')

def edit_activity_view(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    # MODIFIED: Redirect to the correct planner view based on context
    # We will assume editing always goes back to the specific project planner for simplicity.
    redirect_url = reverse('activity_planner', kwargs={'project_pk': activity.project.pk})
    
    # Optional: If you want it to be smarter and redirect to consolidated view if that's where you came from
    # You would need to pass a 'next' parameter in the URL from the template.
    # For now, this is a safe default.
    
    if request.method == 'POST':
        form = ActivityForm(request.POST, instance=activity)
        if form.is_valid():
            form.save()
            # To preserve grouping, you could pass it along, but let's keep it simple.
            return redirect(redirect_url)
    else:
        form = ActivityForm(instance=activity)
        
    context = {'activity': activity, 'form': form, 'project': activity.project}
    return render(request, 'planner/edit_activity.html', context)

def delete_activity_view(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    project_pk = activity.project.pk
    activity.delete()
    return redirect('activity_planner', project_pk=project_pk)

def edit_project_type_view(request, pk):
    project_type = get_object_or_404(ProjectType, pk=pk)
    if request.method == 'POST':
        project_type.segment = get_object_or_404(Segment, pk=request.POST.get('segment'))
        project_type.category = get_object_or_404(Category, pk=request.POST.get('category'))
        project_type.engineer_involvement = request.POST.get('engineer_involvement')
        project_type.team_lead_involvement = request.POST.get('team_lead_involvement')
        project_type.manager_involvement = request.POST.get('manager_involvement')
        project_type.save()
        return redirect('configuration')
    context = {'type': project_type, 'all_segments': Segment.objects.all(), 'all_categories': Category.objects.all()}
    return render(request, 'planner/edit_project_type.html', context)

def delete_project_type_view(request, pk):
    get_object_or_404(ProjectType, pk=pk).delete()
    return redirect('configuration')

def capacity_plan_view(request):
    today = date.today()
    months = [(today.replace(day=1) + timedelta(days=31*i)).replace(day=1) for i in range(12)]
    month_keys = [m.strftime('%Y-%m') for m in months]
    
    general_settings, _ = GeneralSettings.objects.get_or_create(pk=1)
    holidays = list(Holiday.objects.values_list('date', flat=True))
    capacity_settings = {c: CapacitySettings.objects.get_or_create(designation=c)[0] for c, _ in Employee.DESIGNATION_CHOICES}
    workforce_counts = {'ENGINEER': Employee.objects.filter(designation='ENGINEER').count(), 'TEAM_LEAD': Employee.objects.filter(designation='TEAM_LEAD').count(), 'MANAGER': Employee.objects.filter(designation='MANAGER').count()}
    
    supply_data = defaultdict(dict)
    for month in months:
        _, num_days_in_month = calendar.monthrange(month.year, month.month)
        working_days_in_month = count_working_days(date(month.year, month.month, 1), date(month.year, month.month, num_days_in_month), holidays)
        for designation, count in workforce_counts.items():
            settings = capacity_settings[designation]
            month_key = month.strftime('%Y-%m')
            gross_hours = count * working_days_in_month * general_settings.working_hours_per_day
            non_project_hours = count * (settings.monthly_meeting_hours + settings.monthly_leave_hours)
            efficiency_loss = (gross_hours - non_project_hours) * (settings.efficiency_loss_factor / 100)
            supply_data[designation][month_key] = {'available_hours': gross_hours - non_project_hours - efficiency_loss, 'headcount': count}

    demand_hours = defaultdict(lambda: defaultdict(float))
    for activity in Activity.objects.select_related('assignee').filter(assignee__isnull=False, start_date__isnull=False, end_date__isnull=False):
        daily_hours = general_settings.working_hours_per_day
        current_date = activity.start_date
        while current_date <= activity.end_date:
            if current_date.weekday() < 5 and current_date not in holidays:
                demand_hours[activity.assignee.designation][current_date.strftime('%Y-%m')] += daily_hours
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
        current_date = forecast.start_date
        while current_date <= forecast.end_date:
            if current_date.weekday() < 5 and current_date not in holidays:
                month_key = current_date.strftime('%Y-%m')
                demand_hours['ENGINEER'][month_key] += daily_eng_hours
                demand_hours['TEAM_LEAD'][month_key] += daily_tl_hours
                demand_hours['MANAGER'][month_key] += daily_mgr_hours
            current_date += timedelta(days=1)
    
    # NEW: Calculate chart data for capacity requirements
    live_workload_by_month = defaultdict(float)
    forecasted_workload_by_month = defaultdict(float)
    
    # Calculate live/backlog workload from existing activities
    for activity in Activity.objects.select_related('assignee').filter(
        assignee__isnull=False, start_date__isnull=False, end_date__isnull=False
    ):
        current_date = activity.start_date
        while current_date <= activity.end_date:
            if current_date.weekday() < 5 and current_date not in holidays:
                month_key = current_date.strftime('%Y-%m')
                live_workload_by_month[month_key] += general_settings.working_hours_per_day
            current_date += timedelta(days=1)
    
    # Calculate forecasted workload
    for forecast in SalesForecast.objects.filter(start_date__isnull=False, end_date__isnull=False):
        pt_id = pt_map.get((forecast.segment, forecast.category))
        if not pt_id:
            continue
        
        brackets = pt_bracket_map.get(pt_id, [])
        calculated_effort_days = calculate_effort_from_value(forecast.total_amount, brackets)
        if calculated_effort_days <= 0:
            continue
        
        total_window_days = count_working_days(forecast.start_date, forecast.end_date, holidays)
        if total_window_days <= 0:
            continue
        
        daily_effort_factor = calculated_effort_days / total_window_days
        p_type = project_type_map.get(pt_id)
        if not p_type:
            continue
        
        # Total daily hours considering all roles
        total_daily_hours = general_settings.working_hours_per_day * daily_effort_factor * (
            (p_type.engineer_involvement + p_type.team_lead_involvement + p_type.manager_involvement) / 100
        )
        
        current_date = forecast.start_date
        while current_date <= forecast.end_date:
            if current_date.weekday() < 5 and current_date not in holidays:
                month_key = current_date.strftime('%Y-%m')
                forecasted_workload_by_month[month_key] += total_daily_hours
            current_date += timedelta(days=1)
    
    # Prepare chart data
    chart_data = []
    for month in months:
        month_key = month.strftime('%Y-%m')
        month_label = month.strftime('%b %Y')
        
        live_hours = live_workload_by_month.get(month_key, 0)
        forecast_hours = forecasted_workload_by_month.get(month_key, 0)
        
        chart_data.append({
            'month': month_label,
            'live_workload': round(live_hours, 1),
            'forecasted_workload': round(forecast_hours, 1),
            'total': round(live_hours + forecast_hours, 1)
        })
    
    report = []
    for des_value, des_display in Employee.DESIGNATION_CHOICES:
        des_data = {'designation': des_display, 'months': []}
        for month_key in month_keys:
            supply = supply_data[des_value].get(month_key, {})
            available_hours = supply.get('available_hours', 0)
            headcount = supply.get('headcount', 0)
            required_hours = demand_hours[des_value].get(month_key, 0)
            hours_per_person = (available_hours / headcount) if headcount > 0 else 0
            required_headcount = (required_hours / hours_per_person) if hours_per_person > 0 else 0
            des_data['months'].append({
                'month': month_key, 
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
        'chart_data': chart_data  # NEW: Add chart data to context
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
            # Divide by CR to display value in Cr in the modal
            'project_value': bracket.project_value / CR,
            'effort_days': bracket.effort_days
        })
    return JsonResponse({'brackets': brackets_data})

@require_POST
def add_effort_bracket_for_project_type(request, pk):
    project_type = get_object_or_404(ProjectType, pk=pk)
    data = json.loads(request.body)
    try:
        # Multiply by CR to save the full value in the database
        value_in_cr = float(data.get('project_value'))
        full_value = value_in_cr * CR
        
        bracket, created = EffortBracket.objects.update_or_create(
            project_type=project_type,
            project_value=full_value,
            defaults={'effort_days': int(data.get('effort_days'))}
        )
        response_data = {
            'status': 'success', 'id': bracket.id,
            'project_value': bracket.project_value / CR, # Send back in Cr
            'effort_days': bracket.effort_days, 'created': created
        }
        return JsonResponse(response_data)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@require_POST
def delete_effort_bracket_view(request, pk):
    get_object_or_404(EffortBracket, pk=pk).delete()
    return JsonResponse({'status': 'success'})