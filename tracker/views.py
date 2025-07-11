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
    projects = Project.objects.all()
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



@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project.objects.select_related('segment_con'), pk=project_id)

    # Save updates if form submitted
    if request.method == 'POST':
        if 'save_all' in request.POST:
            for stage in project.stages.all():
                new_planned = parse_date(request.POST.get(f'planned_date_{stage.id}'))
                new_status = request.POST.get(f'status_{stage.id}') or "Not started"
                actual_date_val = request.POST.get(f'actual_date_{stage.id}')
                new_actual = parse_date(actual_date_val) if new_status == 'Completed' and actual_date_val else None

                if stage.planned_date != new_planned:
                    StageHistory.objects.create(stage=stage, changed_by=request.user,
                        field_name="Planned Date", old_value=str(stage.planned_date), new_value=str(new_planned))

                if stage.status != new_status:
                    StageHistory.objects.create(stage=stage, changed_by=request.user,
                        field_name="Status", old_value=stage.status, new_value=new_status)

                if stage.actual_date != new_actual:
                    StageHistory.objects.create(stage=stage, changed_by=request.user,
                        field_name="Actual Date", old_value=str(stage.actual_date), new_value=str(new_actual))

                stage.planned_date = new_planned
                stage.status = new_status
                stage.actual_date = new_actual
                stage.save()

            # Clear cache after saving
            cache.delete(f'project_detail_{project_id}')
            messages.success(request, "Changes saved successfully!")
            return redirect(reverse('tracker_project_detail', args=[project.id]))

        else:
            stage_id = request.POST.get('stage_id')
            stage = get_object_or_404(Stage, pk=stage_id, project=project)

            new_planned = parse_date(request.POST.get(f'planned_date_{stage.id}'))
            new_status = request.POST.get(f'status_{stage.id}')
            actual_date_val = request.POST.get(f'actual_date_{stage.id}')
            new_actual = parse_date(actual_date_val) if new_status == 'Completed' and actual_date_val else None

            if stage.planned_date != new_planned:
                StageHistory.objects.create(stage=stage, changed_by=request.user,
                    field_name="Planned Date", old_value=str(stage.planned_date), new_value=str(new_planned))

            if stage.status != new_status:
                StageHistory.objects.create(stage=stage, changed_by=request.user,
                    field_name="Status", old_value=stage.status, new_value=new_status)

            if stage.actual_date != new_actual:
                StageHistory.objects.create(stage=stage, changed_by=request.user,
                    field_name="Actual Date", old_value=str(stage.actual_date), new_value=str(new_actual))

            stage.planned_date = new_planned
            stage.status = new_status
            stage.actual_date = new_actual
            stage.save()

            cache.delete(f'project_detail_{project_id}')
            messages.success(request, "Stage updated successfully!")
            return redirect(reverse('tracker_project_detail', args=[project.id]))

    # Cache section (only GET requests use cache)
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

        context = {
            'project': project,
            'stages': stages,
            'recent_activity': recent_activity,
            'completion_percentage': get_completion_percentage(stages),
            'otif_percentage': get_otif_percentage(stages),
            'overall_status': get_overall_status(stages),
            'schedule_status': get_schedule_status(stages),
            'next_milestone': get_next_milestone(stages),
        }

        # Cache for 20 minutes
        cache.set(cache_key, context, timeout=1200)

    return render(request, 'tracker/project_detail.html', context)



@login_required
def delete_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    project.delete()
    messages.success(request, "Project deleted successfully.")
    return redirect('tracker_index')

@login_required
def dashboard(request):
    projects = Project.objects.all()

    labels = []
    on_track_data = []
    at_risk_data = []
    delayed_data = []

    for project in projects:
        completion = project.get_completion_percentage()
        labels.append(f"{project.code} - {project.customer_name}")

        if completion >= 80:
            on_track_data.append(completion)
            at_risk_data.append(0)
            delayed_data.append(0)
        elif completion >= 40:
            on_track_data.append(0)
            at_risk_data.append(completion)
            delayed_data.append(0)
        else:
            on_track_data.append(0)
            at_risk_data.append(0)
            delayed_data.append(completion)

    return render(request, 'tracker/dashboard.html', {
        'labels': labels,
        'on_track_data': on_track_data,
        'at_risk_data': at_risk_data,
        'delayed_data': delayed_data,
        'total_projects': projects.count(),
        'active_projects': projects.filter(stages__status="In Progress").distinct().count(),
        'delayed_projects': projects.filter(stages__status="Hold").distinct().count(),
        'total_value': sum(p.value for p in projects),
        'recent_projects': projects.order_by('-id')[:5],
    })

@login_required
def project_reports(request):
    stage_names = [name for name, _ in Stage.STAGE_NAMES]
    status_choices = [status for status, _ in Stage.STATUS_CHOICES]

    filters = {}
    for stage in stage_names:
        selected = request.GET.get(stage)
        if selected:
            filters[stage] = selected

    matched_projects = []
    labels = []
    counts = []

    if filters:
        projects = Project.objects.all()
        for project in projects:
            match = True
            for stage_name, required_status in filters.items():
                try:
                    stage = project.stages.get(name=stage_name)
                    if stage.status != required_status:
                        match = False
                        break
                except Stage.DoesNotExist:
                    match = False
                    break
            if match:
                matched_projects.append(project)

        for stage_name in filters:
            label = stage_name
            count = sum(
                1 for p in matched_projects
                if p.stages.filter(name=stage_name, status=filters[stage_name]).exists()
            )
            labels.append(label)
            counts.append(count)

    context = {
        'stage_names': stage_names,
        'status_choices': status_choices,
        'filters': filters,
        'matched_projects': matched_projects,
        'labels': labels,
        'counts': counts
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
