"""The friendly "you don't have access" page shared by every software in AutoVerse.

The per-software access middleware (middleware.py), the Log, and Django's handler403 all
render it. ForbiddenPageMiddleware also swaps it in for any plain-text 403 that a view
returns on a normal page visit, so a person never lands on a bare "Access denied." line.
"""
import re

from django.contrib.auth import get_user_model
from django.template.response import TemplateResponse

# First URL segment -> (software name, emoji), matching the sidebar.
SOFTWARE = {
    'tracker': ('Tracker', '📊'),
    'planner': ('Planner', '🗓️'),
    'inventory': ('Inventory', '📦'),
    'skillgap': ('Skill Gap', '🎯'),
    'estimator': ('Estimator', '🧮'),
    'testvault': ('TestVault', '🧪'),
    'forum': ('Knowledge Base', '💡'),
    'acgen': ('ACGen', '⚙️'),
    'onedesigner': ('One Designer', '🎨'),
    'log': ('Log', '🗂️'),
}
DEFAULT_SOFTWARE = ('this page', '🔒')


def software_for(path):
    first = path.strip('/').split('/')[0].lower()
    return SOFTWARE.get(first, DEFAULT_SOFTWARE)


def _administrators():
    """Active superusers, named, so the person knows who to ask."""
    admins, seen = [], set()
    for u in get_user_model().objects.filter(is_superuser=True, is_active=True).order_by('first_name', 'username'):
        name = u.get_full_name().strip() or u.username
        if name in seen:  # one person with two admin accounts
            continue
        seen.add(name)
        admins.append({'name': name, 'email': u.email})
    return admins[:4]


def access_denied(request, software=None, reason='', how_to_get=''):
    """Renders the access-denied page with status 403.

    software: the name shown in the heading ("Tracker"); worked out from the URL if omitted.
    reason: one sentence on why, in plain words.
    how_to_get: what an administrator has to do, e.g. "tick “Tracker access” on your profile".
    """
    name, emoji = software_for(request.path_info)
    if software:
        name = software
    admins = _administrators()
    contact = next((a for a in admins if a['email']), None)
    response = TemplateResponse(request, 'access_denied.html', {
        'software': name,
        'emoji': emoji,
        'reason': reason,
        'how_to_get': how_to_get,
        'admins': admins,
        'contact': contact,
        'requested_path': request.get_full_path(),
    }, status=403)
    response.is_access_page = True
    # Rendered here: a TemplateResponse returned from middleware isn't rendered for us.
    return response.render()


def permission_denied_view(request, exception=None):
    """handler403: PermissionDenied raised anywhere (e.g. permission_required)."""
    reason = str(exception) if exception and str(exception) else ''
    return access_denied(request, reason=_readable(reason))


def _readable(text):
    """Turns a short plain-text refusal into a sentence worth showing, or ''."""
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if not text or text.lower() in ('403 forbidden', 'forbidden', 'access denied.', 'access denied'):
        return ''
    return text[:300]


class ForbiddenPageMiddleware:
    """Replaces bare 403 responses on normal page visits with the access-denied page.

    Left alone: API / JSON responses, background (XHR / HTMX) requests, the Django admin
    (it has its own page), non-GET requests, and anything already a full page.
    """

    SKIP_PREFIXES = ('/admin/', '/api/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 403 or getattr(response, 'is_access_page', False):
            return response
        if request.method not in ('GET', 'HEAD') or request.path_info.startswith(self.SKIP_PREFIXES):
            return response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('HX-Request'):
            return response
        if 'text/html' not in request.headers.get('Accept', ''):
            return response
        content_type = response.get('Content-Type', '')
        if not content_type.startswith(('text/html', 'text/plain')) or getattr(response, 'streaming', False):
            return response
        body = response.content.decode(response.charset or 'utf-8', errors='ignore')
        if len(body) > 2000 or '<body' in body.lower():
            return response  # already a real page
        return access_denied(request, reason=_readable(body))
