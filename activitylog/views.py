from collections import defaultdict
from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from openpyxl import Workbook
from openpyxl.styles import Font

from .models import ActivityLog

PAGE_SIZE = 50
EXPORT_LIMIT = 50000


def _filtered_entries(params):
    """Applies the page's filters (default: the last 7 days) and returns
    (queryset, start_date, end_date, the cleaned filter values)."""
    today = timezone.localdate()
    start = parse_date(params.get('start') or '') or (today - timedelta(days=6))
    end = parse_date(params.get('end') or '') or today
    tz = timezone.get_current_timezone()
    window = (
        timezone.make_aware(datetime.combine(start, time.min), tz),
        timezone.make_aware(datetime.combine(end, time.max), tz),
    )
    entries = ActivityLog.objects.filter(timestamp__range=window)
    filters = {k: (params.get(k) or '').strip() for k in ('user', 'app', 'event', 'q')}

    if filters['user']:
        entries = entries.filter(username=filters['user'])
    if filters['app']:
        entries = entries.filter(app=filters['app'])
    if filters['event']:
        entries = entries.filter(event=filters['event'])
    if filters['q']:
        q = filters['q']
        entries = entries.filter(
            Q(description__icontains=q) | Q(path__icontains=q) | Q(username__icontains=q)
        )
    return entries, start, end, filters, window


def _export(entries):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Log'
    sheet.append(['Time', 'User', 'Event', 'Software', 'Activity', 'Page', 'Method', 'Status', 'IP address'])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for e in entries.order_by('-timestamp')[:EXPORT_LIMIT]:
        sheet.append([
            timezone.localtime(e.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
            e.username, e.get_event_display(), e.app, e.description, e.path,
            e.method, e.status_code, e.ip_address or '',
        ])
    for column in sheet.columns:
        width = max((len(str(c.value)) for c in column if c.value is not None), default=10)
        sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 60)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="AutoVerse_Log_{timezone.localtime():%Y-%m-%d_%H-%M}.xlsx"'
    workbook.save(response)
    return response


@login_required
def log_list(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('Access denied. The Log is for administrators only.')

    entries, start, end, filters, window = _filtered_entries(request.GET)

    if request.GET.get('export') == '1':
        return _export(entries)

    tab = 'users' if request.GET.get('tab') == 'users' else 'activity'
    E = ActivityLog.Event

    totals = entries.aggregate(
        total=Count('id'),
        logins=Count('id', filter=Q(event=E.LOGIN)),
        failed=Count('id', filter=Q(event=E.LOGIN_FAILED)),
        actions=Count('id', filter=Q(event=E.ACTION)),
        denied=Count('id', filter=Q(event=E.DENIED)),
    )
    totals['users'] = entries.exclude(username='').values('username').distinct().count()

    # Dropdown choices come from the date window only, so narrowing one filter doesn't
    # empty the others.
    in_window = ActivityLog.objects.filter(timestamp__range=window)
    usernames = list(in_window.exclude(username='').values_list('username', flat=True).distinct().order_by('username'))
    apps = list(in_window.exclude(app='').values_list('app', flat=True).distinct().order_by('app'))

    context = {
        'tab': tab, 'totals': totals, 'filters': filters,
        'start': start, 'end': end,
        'usernames': usernames, 'apps': apps, 'event_choices': E.choices,
    }

    params = request.GET.copy()
    params.pop('page', None)
    params.pop('tab', None)
    context['filter_query'] = params.urlencode()

    if tab == 'users':
        rows = list(
            entries.exclude(username='').values('username').annotate(
                last_seen=Max('timestamp'),
                logins=Count('id', filter=Q(event=E.LOGIN)),
                failed=Count('id', filter=Q(event=E.LOGIN_FAILED)),
                views=Count('id', filter=Q(event=E.VIEW)),
                actions=Count('id', filter=Q(event=E.ACTION)),
                downloads=Count('id', filter=Q(event=E.DOWNLOAD)),
            ).order_by('-last_seen')
        )
        apps_by_user = defaultdict(set)
        for username, app in entries.exclude(username='').exclude(app='').values_list('username', 'app').distinct():
            apps_by_user[username].add(app)
        for row in rows:
            row['apps'] = ', '.join(sorted(apps_by_user[row['username']]))
        context['user_rows'] = rows
    else:
        page = Paginator(entries.select_related('user'), PAGE_SIZE).get_page(request.GET.get('page'))
        context['page'] = page

    return render(request, 'activitylog/log_list.html', context)
