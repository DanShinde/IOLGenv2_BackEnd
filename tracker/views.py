from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Project, Stage, StageHistory, trackerSegment
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import render
from .models import Stage
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from .models import StageRemark

from tracker.utils import (
    get_completion_percentage,
    get_otif_percentage,
    get_overall_status,
    get_schedule_status,
    get_next_milestone
)
from django.db.models import Prefetch
from django.core.cache import cache


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
    return redirect('loginw')

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "User registered successfully! Please log in.")
            return redirect('loginw')
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
            messages.error(request, "Project code already exists. Please use a different code.")
            return render(request, 'tracker/project_form.html', {
                'segments': trackerSegment.objects.all()
            })
        segment_id = request.POST.get('segment')
        segment_con = trackerSegment.objects.get(id=segment_id) if segment_id else None
        project = Project.objects.create(
            code=code,
            customer_name=request.POST['customer_name'],
            value=request.POST['value'],
            so_punch_date=parse_date(request.POST['so_punch_date']),
            segment_con=segment_con
        )
        for stage_name, _ in Stage.STAGE_NAMES:
            Stage.objects.create(project=project, name=stage_name)
        messages.success(request, "Project created successfully!")
        return redirect('tracker_project_detail', project_id=project.id)
    return render(request, 'tracker/project_form.html', {
        'segments': trackerSegment.objects.all()
    })



# tracker/views.py

@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project.objects.select_related('segment_con'), pk=project_id)

    if request.method == 'POST':
        # ... all the existing POST handling logic remains the same ...
        if 'save_all' in request.POST:
            for stage in project.stages.all():
                # ... (no changes needed here) ...
                stage.save()
            cache.delete(f'project_detail_{project_id}')
            messages.success(request, "Changes saved successfully!")
            return redirect(reverse('tracker_project_detail', args=[project.id]))
        else:
            # ... (no changes needed in the single stage save logic either) ...
            stage.save()
            cache.delete(f'project_detail_{project_id}')
            messages.success(request, "Stage updated successfully!")
            return redirect(reverse('tracker_project_detail', args=[project.id]))

    cache_key = f'project_detail_{project_id}'
    context = cache.get(cache_key)

    if not context:
        stages = list(
            Stage.objects.filter(project=project)
            .prefetch_related('remarks', 'history')
            .order_by('id')
        )
        recent_activity = StageHistory.objects.select_related(
            'stage', 'changed_by'
        ).filter(stage__project=project).order_by('-changed_at')[:2]
        
        # ✅ ADD THIS LOGIC to safely get the last update time
        last_update_obj = StageHistory.objects.filter(stage__project=project).order_by('-changed_at').first()
        last_update_time = last_update_obj.changed_at if last_update_obj else project.so_punch_date

        context = {
            'project': project,
            'stages': stages,
            'recent_activity': recent_activity,
            'completion_percentage': get_completion_percentage(stages),
            'otif_percentage': get_otif_percentage(stages),
            'overall_status': get_overall_status(stages),
            'schedule_status': get_schedule_status(stages),
            'next_milestone': get_next_milestone(stages),
            'last_update_time': last_update_time, # ✅ PASS it to the template
        }
        cache.set(cache_key, context, timeout=1200)

    return render(request, 'tracker/project_detail.html', context)

@login_required
def delete_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    project.delete()
    messages.success(request, "Project deleted successfully.")
    return redirect('tracker_index')



from django.db.models import F, Sum, Count
from collections import Counter
from dateutil.relativedelta import relativedelta

@login_required
def dashboard(request):
    # --- Date Filter Logic ---
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
            '7d': ("Last 7 Days", today - timedelta(days=7), today),
            '30d': ("Last 30 Days", today - timedelta(days=30), today),
            'this_month': ("Current Month", today.replace(day=1), today),
            'this_year': ("Current Year", today.replace(day=1, month=1), today),
            'all': ("All Time", None, None),
        }
        display_period, start_date, end_date = period_map.get(period, ("Last 30 Days", today - timedelta(days=30), today))

    # --- "Live Projects" Filter Logic ---
    if period == 'all' and not (custom_start and custom_end):
        live_projects = Project.objects.all().distinct()
    else:
        completed_early_ids = Project.objects.filter(
            stages__name='Handover', stages__status='Completed', stages__actual_date__lt=start_date
        ).values_list('id', flat=True)
        live_projects = Project.objects.filter(so_punch_date__lte=end_date).exclude(id__in=completed_early_ids).distinct()

    # --- ✅ NEW: Chronic Projects Filter Logic ---
    chronic_period = request.GET.get('chronic_period', '1y')
    chronic_cutoff_date = today
    if chronic_period == '6m':
        chronic_cutoff_date = today - relativedelta(months=6)
    elif chronic_period == '1y':
        chronic_cutoff_date = today - relativedelta(years=1)
    elif chronic_period == '2y':
        chronic_cutoff_date = today - relativedelta(years=2)

    chronic_projects = Project.objects.exclude(
        stages__name='Handover', stages__status='Completed'
    ).filter(
        so_punch_date__lt=chronic_cutoff_date
    ).select_related('segment_con').order_by('so_punch_date')


    # --- All other calculations remain the same ---
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
        'total_projects': total_live_projects, 'active_projects': active_live_projects,
        'delayed_projects': delayed_live_projects, 'total_value': total_live_value,
        'department_otif': department_otif,
        'recent_projects': Project.objects.all().order_by('-so_punch_date')[:5],
        'labels': labels, 'on_track_data': on_track_data, 'at_risk_data': at_risk_data, 'delayed_data': delayed_data,
        'status_labels': status_labels, 'status_data': status_data,
        'selected_period_display': display_period,
        'custom_start_date': custom_start, 'custom_end_date': custom_end,
        
        # ✅ Add new variables for chronic projects to the context
        'chronic_projects': chronic_projects,
        'selected_chronic_period': chronic_period,
    }
    return render(request, 'tracker/dashboard.html', context)

@login_required
def project_reports(request):
    projects = Project.objects.select_related('segment_con').prefetch_related('stages').all()

    # --- Get standard filter values ---
    selected_segment_ids = request.GET.getlist('segments')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if selected_segment_ids:
        projects = projects.filter(segment_con__id__in=selected_segment_ids)
    
    if start_date and end_date:
        projects = projects.filter(so_punch_date__range=[start_date, end_date])

    # --- NEW: Process Stage-Specific Filters ---
    stage_filters_from_request = {}
    for stage_key, stage_display in Stage.STAGE_NAMES:
        status = request.GET.get(f'stage_{stage_key}_status')
        start = request.GET.get(f'stage_{stage_key}_start')
        end = request.GET.get(f'stage_{stage_key}_end')

        if status or (start and end):
            # Store the user's selections to send back to the template
            stage_filters_from_request[stage_key] = {'status': status, 'start': start, 'end': end}
            
            # Prepare the query for this specific stage
            stage_query_filters = {'stages__name': stage_key}
            if status:
                stage_query_filters['stages__status'] = status
            if start and end:
                stage_query_filters['stages__actual_date__range'] = [start, end]
            
            # Apply the filter for this stage
            projects = projects.filter(**stage_query_filters)
            

    # --- Calculate KPIs (no changes here) ---
    total_projects_found = projects.distinct().count()
    total_portfolio_value = projects.distinct().aggregate(total_value=Sum('value'))['total_value'] or 0
    
    # We use distinct projects for calculations
    distinct_projects = projects.distinct()
    completion_percentages = [p.get_completion_percentage() for p in distinct_projects]
    average_completion = sum(completion_percentages) / total_projects_found if total_projects_found > 0 else 0

    # --- Prepare chart data (no changes here) ---
    status_counts = Counter(p.get_overall_status() for p in distinct_projects)
    status_labels = list(status_counts.keys())
    status_data = list(status_counts.values())

    segment_counts = distinct_projects.values('segment_con__name').annotate(count=Count('id')).order_by('-count')
    segment_labels = [item['segment_con__name'] for item in segment_counts if item['segment_con__name']]
    segment_data = [item['count'] for item in segment_counts if item['segment_con__name']]

    context = {
        'projects': distinct_projects,
        'total_projects_found': total_projects_found,
        'total_portfolio_value': total_portfolio_value,
        'average_completion': average_completion,
        'all_segments': trackerSegment.objects.all(),
        'selected_segment_ids': [int(i) for i in selected_segment_ids],
        'start_date': start_date,
        'end_date': end_date,
        'status_labels': status_labels,
        'status_data': status_data,
        'segment_labels': segment_labels,
        'segment_data': segment_data,
        # NEW: Pass stage info and selected filters to the template
        'stage_names': Stage.STAGE_NAMES,
        'status_choices': Stage.STATUS_CHOICES,
        'stage_filters': stage_filters_from_request,
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

@login_required
def upcoming_milestones(request):
    filter_type = request.GET.get('filter', 'all')
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
        stages = Stage.objects.filter(status__in=["Not started", "In Progress"], planned_date__lt=today)
    elif filter_type in date_ranges:
        start, end = date_ranges[filter_type]
        stages = Stage.objects.filter(status__in=["Not started", "In Progress"], planned_date__range=(start, end))
    elif filter_type == 'all':
        stages = Stage.objects.filter(status__in=["Not started", "In Progress", "Hold"])

    else:
        stages = Stage.objects.filter(status__in=["Not started", "In Progress"], planned_date__gte=today)
        

    stages = stages.order_by('planned_date')

    return render(request, 'tracker/upcoming_milestones.html', {
        'upcoming': stages,
        'filter_type': filter_type,
        'filter_options': [
            ('All', 'all'),
            ('Overdue', 'overdue'),
            ('Today', 'today'),
            ('Tomorrow', 'tomorrow'),
            ('This Week', 'this_week'),
            ('Next Week', 'next_week'),
            ('This Month', 'this_month'),
            ('Next Month', 'next_month'),
        ],
        'today': today,  # ✅ add this line
        })



import csv
from django.http import HttpResponse
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime


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



from django.http import HttpResponse
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime


@login_required
def export_report_pdf(request):
    # This logic is a copy of the filtering from the main reports page
    # to ensure we get the exact same list of projects.
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