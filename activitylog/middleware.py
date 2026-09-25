import logging

from .changes import collect_changes
from .models import ActivityLog
from .services import denied_title, describe, record_event, title_for_changes

logger = logging.getLogger(__name__)

# Never logged: assets, tooling, the Log page itself (viewing it would only add noise), and
# the sign-in/out endpoints, which are recorded by the auth signals instead.
SKIP_PREFIXES = (
    '/static/', '/media/', '/__debug__/', '/log/', '/deploy-hook/', '/favicon',
    '/admin/jsi18n/', '/accounts/loginw/', '/accounts/logoutw/', '/accounts/login/',
    '/accounts/token/',
)
WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


class ActivityLogMiddleware:
    """Records what signed-in people do, across every software in AutoVerse.

    Sits directly after AuthenticationMiddleware -- outside the per-software access
    middleware -- so a refused request (403) is still seen. Logged: page views (full HTML
    pages, not background/HTMX fetches), every change (POST/PUT/PATCH/DELETE, including
    inline autosaves), file downloads, and access-denied responses.

    While a change request runs, the records it saves are compared field by field (see
    changes.py), so the entry can say "Planned date changed, 12 Oct -> 19 Oct" instead of
    naming the URL.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if request.method in WRITE_METHODS and not path.startswith(SKIP_PREFIXES):
            with collect_changes() as records:
                response = self.get_response(request)
        else:
            records = []
            response = self.get_response(request)
        try:
            self._log(request, response, records)
        except Exception:
            logger.exception('Activity logging failed')
        return response

    def _log(self, request, response, records):
        path = request.path_info
        if path.startswith(SKIP_PREFIXES):
            return
        # Read after the response: DRF assigns the JWT-authenticated user to the underlying
        # request, so API calls made by the desktop app are attributed to the right person.
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return

        status = response.status_code
        method = request.method
        background = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.headers.get('HX-Request')
        )

        if status == 403:
            event = ActivityLog.Event.DENIED
        elif method in ('GET', 'HEAD'):
            if 'attachment' in response.get('Content-Disposition', ''):
                event = ActivityLog.Event.DOWNLOAD
            elif status == 200 and not background and response.get('Content-Type', '').startswith('text/html'):
                event = ActivityLog.Event.VIEW
            else:
                return
        elif method in WRITE_METHODS:
            event = ActivityLog.Event.ACTION
        else:
            return

        title, target = describe(request)
        changes = []
        # A refused or failed change saved nothing worth reporting as done.
        if event == ActivityLog.Event.ACTION and records and status < 400:
            title, event = title_for_changes(records)
            target = records[0]['object']
            changes = records
        elif event == ActivityLog.Event.DENIED:
            title = denied_title(title)

        record_event(event, request=request, user=user, description=title,
                     target=target, changes=changes, status_code=status)
