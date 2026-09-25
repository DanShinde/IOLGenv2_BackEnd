import ipaddress
import logging
import re

from .models import ActivityLog

logger = logging.getLogger(__name__)

# First URL segment -> the software it belongs to, as named in the sidebar.
APP_BY_PREFIX = {
    '': 'Home',
    'tracker': 'Tracker',
    'planner': 'Planner',
    'inventory': 'Inventory',
    'skillgap': 'Skill Gap',
    'estimator': 'Estimator',
    'testvault': 'TestVault',
    'forum': 'Knowledge Base',
    'acgen': 'ACGen',
    'onedesigner': 'One Designer',
    'accounts': 'Accounts',
    'admin': 'Admin',
    'downloads': 'Downloads',
    'cacheclear': 'Home',
    'ckeditor': 'Uploads',
}

# Leading words of a URL name that just repeat the software name ("tracker_add_phase").
_APP_WORDS = {'tracker', 'planner', 'inventory', 'skillgap', 'estimator', 'testvault',
              'forum', 'kb', 'acgen', 'admin', 'home'}


def resolve_app(path):
    first = path.strip('/').split('/')[0].lower()
    return APP_BY_PREFIX.get(first, 'Other')


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')
    try:
        return str(ipaddress.ip_address(ip))
    except (ValueError, TypeError):
        return None


def describe(request):
    """Turns the matched URL into something readable, e.g. tracker_add_phase -> "Add Phase"
    (project_id=12). Only ids from the URL are included -- never form data or query strings,
    which can carry passwords or tokens."""
    match = getattr(request, 'resolver_match', None)
    if not match:
        return request.path_info[:255]
    name = (match.view_name or match.url_name or getattr(match.func, '__name__', '')).replace(':', '_')
    words = [w for w in re.split(r'[_\-\s]+', name) if w]
    while words and words[0].lower() in _APP_WORDS:
        words = words[1:]
    label = ' '.join(w.capitalize() for w in words) or request.path_info
    ids = ', '.join(
        f"{k}={v}" for k, v in match.kwargs.items()
        if 'token' not in k.lower() and len(str(v)) <= 40
    )
    return (f"{label} ({ids})" if ids else label)[:255]


def record_event(event, request=None, user=None, username='', description='', status_code=None):
    """Writes one log row. Never raises: logging must not be able to break a request."""
    try:
        if user is not None and not getattr(user, 'is_authenticated', False):
            user = None
        entry = ActivityLog(
            event=event,
            user=user,
            username=(username or (user.get_username() if user else ''))[:150],
            description=description[:255],
            status_code=status_code,
        )
        if request is not None:
            entry.path = request.path_info[:500]
            entry.method = request.method[:10]
            entry.app = resolve_app(request.path_info)
            match = getattr(request, 'resolver_match', None)
            entry.view_name = (match.view_name if match else '')[:150]
            entry.ip_address = client_ip(request)
            entry.user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
        entry.save()
    except Exception:
        logger.exception('Could not write activity log entry')
