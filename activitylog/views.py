from collections import defaultdict
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from openpyxl import Workbook
from openpyxl.styles import Font

from .models import ActivityLog

PAGE_SIZE = 50
EXPORT_LIMIT = 50000
E = ActivityLog.Event
# Page visits outnumber everything else, so they're hidden until asked for.
DEFAULT_EVENTS = [value for value, _ in E.choices if value != E.VIEW]
# Order of the type chips on the page.
EVENT_ORDER = [E.CREATE, E.UPDATE, E.DELETE, E.ACTION, E.DOWNLOAD, E.LOGIN, E.LOGOUT,
               E.LOGIN_FAILED, E.DENIED]
WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _filtered_entries(params):
    """Applies the page's filters (default: the last 7 days, everything except page visits).

    Returns (entries, base, selected events, start, end, filters, window), where `base` has
    every filter except the type chips -- the chip counts and the insight strip use it, so
    switching a type off doesn't make the charts or its own count vanish."""
    today = timezone.localdate()
    start = parse_date(params.get('start') or '') or (today - timedelta(days=6))
    end = parse_date(params.get('end') or '') or today
    tz = timezone.get_current_timezone()
    window = (
        timezone.make_aware(datetime.combine(start, time.min), tz),
        timezone.make_aware(datetime.combine(end, time.max), tz),
    )
    base = ActivityLog.objects.filter(timestamp__range=window)
    filters = {k: (params.get(k) or '').strip() for k in ('user', 'app', 'q')}

    if filters['user']:
        base = base.filter(username=filters['user'])
    if filters['app']:
        base = base.filter(app=filters['app'])
    if filters['q']:
        q = filters['q']
        base = base.filter(
            Q(description__icontains=q) | Q(target__icontains=q) | Q(path__icontains=q)
            | Q(username__icontains=q) | Q(full_name__icontains=q)
        )

    # 'f' marks a submitted filter form, so unticking every type means "none", not "default".
    valid = {value for value, _ in E.choices}
    if 'f' in params:
        selected = [e for e in params.getlist('event') if e in valid]
    elif params.get('event') in valid:  # links from the People summary tab
        selected = [params['event']]
    else:
        selected = list(DEFAULT_EVENTS)
    entries = base.filter(event__in=selected)
    return entries, base, selected, start, end, filters, window


def _names_for(usernames):
    """username -> "First Last" from the accounts; missing when the account has no name."""
    users = get_user_model().objects.filter(username__in=set(usernames))
    return {u.username: u.get_full_name().strip() for u in users if u.get_full_name().strip()}


def _export(entries):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Log'
    sheet.append(['Time', 'Person', 'Username', 'Type', 'What happened', 'Record', 'Changes',
                  'Software', 'Page', 'Method', 'Status', 'IP address'])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for e in entries.select_related('user').order_by('-timestamp')[:EXPORT_LIMIT]:
        sheet.append([
            timezone.localtime(e.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
            e.person_name, e.username, e.get_event_display(), e.description, e.target,
            e.changes_text(), e.app, e.path, e.method, e.status_code, e.ip_address or '',
        ])
    for column in sheet.columns:
        width = max((len(str(c.value)) for c in column if c.value is not None), default=10)
        sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 60)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="AutoVerse_Log_{timezone.localtime():%Y-%m-%d_%H-%M}.xlsx"'
    workbook.save(response)
    return response


def _heatmap(base):
    """Entries per weekday and hour, as 7 rows of 24 cells with a 0-4 shade level."""
    counts = {
        (row['wd'], row['h']): row['n']
        for row in base.annotate(wd=ExtractIsoWeekDay('timestamp'), h=ExtractHour('timestamp'))
                       .values('wd', 'h').annotate(n=Count('id'))
    }
    peak = max(counts.values(), default=0)
    rows = []
    for wd, label in enumerate(WEEKDAYS, start=1):
        cells = []
        for hour in range(24):
            n = counts.get((wd, hour), 0)
            level = 0 if not n else min(4, 1 + int(3 * n / peak)) if peak else 0
            cells.append({'hour': hour, 'n': n, 'level': level})
        rows.append({'day': label, 'cells': cells, 'total': sum(c['n'] for c in cells)})
    hour_totals = [sum(counts.get((wd, h), 0) for wd in range(1, 8)) for h in range(24)]
    busiest = max(counts, key=counts.get) if counts else None
    return {
        'rows': rows,
        'hour_totals': hour_totals,
        'total': sum(counts.values()),
        'busiest': f"{WEEKDAYS[busiest[0] - 1]} {busiest[1]:02d}:00 ({counts[busiest]})" if busiest else '',
    }


def _by_software(base):
    """Changes per software, split into created / changed / deleted / other."""
    per_app = defaultdict(lambda: {'CREATE': 0, 'UPDATE': 0, 'DELETE': 0, 'ACTION': 0})
    for row in base.filter(event__in=ActivityLog.CHANGE_EVENTS).exclude(app='').values('app', 'event').annotate(n=Count('id')):
        per_app[row['app']][row['event']] = row['n']
    rows = [{'app': app, **c, 'total': sum(c.values())} for app, c in per_app.items()]
    rows.sort(key=lambda r: -r['total'])
    peak = rows[0]['total'] if rows else 1
    for r in rows:
        for key in ('CREATE', 'UPDATE', 'DELETE', 'ACTION'):
            r[f'{key}_pct'] = round(100 * r[key] / peak, 1)
    return rows


def _top_people(base, names):
    """Everyone who changed something, most changes first, split by kind of change."""
    rows = list(
        base.filter(event__in=ActivityLog.CHANGE_EVENTS).exclude(username='')
            .values('username').annotate(
                n=Count('id'),
                created=Count('id', filter=Q(event=E.CREATE)),
                updated=Count('id', filter=Q(event=E.UPDATE)),
                deleted=Count('id', filter=Q(event=E.DELETE)),
                other=Count('id', filter=Q(event=E.ACTION)),
                last=Max('timestamp'),
            ).order_by('-n', 'username')
    )
    peak = rows[0]['n'] if rows else 1
    for r in rows:
        r['name'] = names.get(r['username']) or r['username']
        r['pct'] = round(100 * r['n'] / peak, 1)
        for key in ('created', 'updated', 'deleted', 'other'):
            r[f'{key}_pct'] = round(100 * r[key] / peak, 1)
    return rows


def _change_summary(changes):
    """(first field change, how many more things changed) for the table's Change column."""
    first, total = None, 0
    for i, record in enumerate(changes):
        action = record.get('action')
        if action == 'update':
            for f in record.get('fields', []):
                first = first or f
                total += 1
        elif action == 'more':
            total += record.get('count', 0)
        elif i:  # extra records created or deleted alongside the main one
            total += 1
    return first, max(0, total - (1 if first else 0))


def _row(e, names):
    local = timezone.localtime(e.timestamp)
    first_change, more = _change_summary(e.changes or [])
    today = timezone.localdate()
    prefix = {today: 'Today · ', today - timedelta(days=1): 'Yesterday · '}.get(local.date(), '')
    return {
        'day_label': prefix + local.strftime('%A %d %b %Y'),
        'first_change': first_change,
        'more': more,
        'id': e.pk,
        'date': local.strftime('%Y-%m-%d'),
        'when': local.strftime('%d %b %Y, %H:%M:%S'),
        'time': local.strftime('%H:%M'),
        'person': e.full_name or names.get(e.username, ''),
        'username': e.username,
        'event': e.event,
        'event_label': e.get_event_display(),
        'app': e.app,
        'title': e.description,
        'target': e.target,
        'changes': e.changes or [],
        'path': e.path,
        'method': e.method,
        'status': e.status_code,
        'ip': e.ip_address or '',
        'agent': e.user_agent,
    }


@login_required
def log_list(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('Access denied. The Log is for administrators only.')

    entries, base, selected, start, end, filters, window = _filtered_entries(request.GET)

    if request.GET.get('export') == '1':
        return _export(entries)

    tab = 'users' if request.GET.get('tab') == 'users' else 'activity'

    totals = base.aggregate(
        changes=Count('id', filter=Q(event__in=ActivityLog.CHANGE_EVENTS)),
        created=Count('id', filter=Q(event=E.CREATE)),
        updated=Count('id', filter=Q(event=E.UPDATE)),
        deleted=Count('id', filter=Q(event=E.DELETE)),
        downloads=Count('id', filter=Q(event=E.DOWNLOAD)),
        failed=Count('id', filter=Q(event=E.LOGIN_FAILED)),
        denied=Count('id', filter=Q(event=E.DENIED)),
    )
    totals['users'] = base.exclude(user=None).values('username').distinct().count()

    # Dropdown choices come from the date window only, so narrowing one filter doesn't
    # empty the others.
    in_window = ActivityLog.objects.filter(timestamp__range=window)
    usernames = list(in_window.exclude(username='').values_list('username', flat=True).distinct().order_by('username'))
    names = _names_for(usernames)
    people = sorted(
        ({'username': u, 'name': names.get(u, '')} for u in usernames),
        key=lambda p: (not p['name'], (p['name'] or p['username']).lower()),
    )
    apps = list(in_window.exclude(app='').values_list('app', flat=True).distinct().order_by('app'))

    counts = dict(base.values_list('event').annotate(n=Count('id')))
    labels = dict(E.choices)
    chips = [{'value': ev, 'label': labels[ev], 'count': counts.get(ev, 0), 'on': ev in selected}
             for ev in EVENT_ORDER]

    context = {
        'tab': tab, 'totals': totals, 'filters': filters, 'start': start, 'end': end,
        'people': people, 'apps': apps, 'chips': chips,
        'views_on': E.VIEW in selected, 'view_count': counts.get(E.VIEW, 0),
        'heatmap': _heatmap(base), 'hours': range(24),
        'by_software': _by_software(base), 'top_people': _top_people(base, names),
    }

    params = request.GET.copy()
    params.pop('page', None)
    params.pop('tab', None)
    if 'f' not in params:
        # Keep the chosen types when paging or switching tab, even from a default view.
        params.setlist('event', selected)
        params['f'] = '1'
    context['filter_query'] = params.urlencode()

    if tab == 'users':
        rows = list(
            base.exclude(username='').values('username').annotate(
                last_seen=Max('timestamp'),
                logins=Count('id', filter=Q(event=E.LOGIN)),
                failed=Count('id', filter=Q(event=E.LOGIN_FAILED)),
                views=Count('id', filter=Q(event=E.VIEW)),
                changes=Count('id', filter=Q(event__in=ActivityLog.CHANGE_EVENTS)),
                downloads=Count('id', filter=Q(event=E.DOWNLOAD)),
            ).order_by('-last_seen')
        )
        apps_by_user = defaultdict(set)
        for username, app in base.exclude(username='').exclude(app='').values_list('username', 'app').distinct():
            apps_by_user[username].add(app)
        for row in rows:
            row['name'] = names.get(row['username'], '')
            row['apps'] = ', '.join(sorted(apps_by_user[row['username']]))
        context['user_rows'] = rows
    else:
        page = Paginator(entries.select_related('user'), PAGE_SIZE).get_page(request.GET.get('page'))
        rows = [_row(e, names) for e in page]
        context['page'] = page
        context['rows'] = rows

    return render(request, 'activitylog/log_list.html', context)
