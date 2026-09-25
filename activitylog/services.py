import ipaddress
import logging
import re

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import Resolver404, resolve

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
# Words that say how a page is served, not what it does ("update_stage_ajax").
_NOISE_WORDS = {'ajax', 'api', 'view', 'page', 'json', 'htmx', 'partial'}

# Verb in a URL name -> the past tense used in the log ("add_phase" -> "Phase added").
_VERBS = {
    'add': 'added', 'new': 'created', 'create': 'created',
    'edit': 'updated', 'update': 'updated', 'save': 'saved', 'change': 'changed', 'set': 'set',
    'delete': 'deleted', 'remove': 'removed',
    'toggle': 'toggled', 'archive': 'archived', 'restore': 'restored',
    'export': 'exported', 'download': 'downloaded', 'import': 'imported', 'upload': 'uploaded',
    'send': 'sent', 'email': 'emailed', 'approve': 'approved', 'reject': 'rejected',
    'assign': 'assigned', 'copy': 'copied', 'duplicate': 'duplicated', 'clone': 'cloned',
    'generate': 'generated', 'reorder': 'reordered', 'move': 'moved', 'close': 'closed',
    'reopen': 'reopened', 'submit': 'submitted', 'sync': 'synced', 'clear': 'cleared',
    'vote': 'voted on', 'cancel': 'cancelled', 'return': 'returned', 'fulfill': 'fulfilled',
    'relieve': 'relieved', 'publish': 'published', 'resolve': 'resolved', 'accept': 'accepted',
}

# URL names whose automatic phrase reads badly. Keyed by the URL name (not namespaced).
TITLES = {
    'home': 'Opened the Home page',
    'tracker_index': 'Opened the project list',
    'tracker_project_detail': 'Opened project',
    'tracker_dashboard': 'Opened the dashboard',
    'project_reports': 'Opened project reports',
    'tracker_new_project': 'Project created',
    'toggle_archive_project': 'Project archived / restored',
    'update_stage_ajax': 'Stage updated',
    'save_stage_delay_reason_ajax': 'Delay reason saved',
    'tracker_add_remark': 'Remark added',
    'send_push_pull_email': 'Push / pull email sent',
    'save_report_preset': 'Report filter saved',
    'delete_report_preset': 'Report filter deleted',
    'toggle_update_status': 'Project update status changed',
    'save_mitigation_plan': 'Mitigation plan saved',
    'help_page': 'Opened help',
}

# URL keyword -> model, where the keyword doesn't name the model itself.
_KWARG_MODELS = {
    'emp': 'employees.Employee',
    'preset': 'tracker.SavedReportFilter',
    'report': 'testvault.ReportSession',
}

# --- Change tracking -------------------------------------------------------------------
# Which apps' records are followed field by field while a request is being handled.
TRACKED_APPS = {'tracker', 'planner', 'inventory', 'estimator', 'testvault', 'gap_analysis',
                'employees', 'home', 'ACGen', 'IOLGen', 'accounts'}
# Records that are themselves a history, or written in bulk as a side effect.
_UNTRACKED_MODEL_SUFFIXES = ('history', 'historyentry', 'log', 'notification', 'importrow')
_SKIPPED_FIELD_WORDS = ('password', 'token', 'secret')
_SKIPPED_FIELD_NAMES = {'id', 'created_at', 'updated_at', 'modified_at', 'last_modified', 'modified'}
# One request can save hundreds of rows (imports, cascades). Only the first few are
# compared field by field; the rest are counted.
MAX_TRACKED_OBJECTS = 25
MAX_VALUE_LENGTH = 80


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


def full_name_for(user=None, username=''):
    """First and last name of the account, or '' when there is none (e.g. a failed sign-in
    with a name that doesn't exist)."""
    if user is None and username:
        user = get_user_model().objects.filter(username__iexact=username).first()
    if user is None:
        return ''
    return (user.get_full_name() or '').strip()


# --- Readable titles --------------------------------------------------------------------

def _url_name(match):
    return (match.url_name or getattr(match.func, '__name__', '') or '').replace(':', '_')


def _words(name):
    words = [w.lower() for w in re.split(r'[_\-\s]+', name) if w]
    while words and words[0] in _APP_WORDS:
        words = words[1:]
    return [w for w in words if w not in _NOISE_WORDS]


def phrase_for(match, method):
    """A readable phrase for a page, from its URL name: "tracker_add_phase" -> "Phase
    added", a GET of "planner_capacity_plan" -> "Opened capacity plan"."""
    name = _url_name(match)
    reading = method in ('GET', 'HEAD')
    if name in TITLES and (reading or not TITLES[name].startswith('Opened')):
        return TITLES[name]
    words = _words(name)
    if not words:
        return ''
    verb_at = next((i for i, w in enumerate(words) if w in _VERBS), None)
    if verb_at is not None:
        verb = words[verb_at]
        subject = ' '.join(w for i, w in enumerate(words) if i != verb_at) or 'item'
        if method not in ('GET', 'HEAD') or verb in ('export', 'download'):
            return f"{subject.capitalize()} {_VERBS[verb]}"
        if verb in ('edit', 'update', 'change'):
            return f"Opened {subject} for editing"
        if verb in ('add', 'new', 'create'):
            return f"Opened new {subject} form"
        if verb in ('delete', 'remove'):
            return f"Opened delete confirmation for {subject}"
    label = ' '.join(words)
    return f"Opened {label}" if reading else f"Submitted {label} form"


def _model_for_kwarg(app_label, key, match):
    base = re.sub(r'_(id|pk)$', '', key).lower()
    if base == 'pk':
        model = getattr(getattr(match.func, 'view_class', None), 'model', None)
        if model is not None:
            return model
        # A function view: guess the record from the URL name ("edit_activity" -> Activity).
        base = None
    if base in _KWARG_MODELS:
        try:
            return apps.get_model(_KWARG_MODELS[base])
        except LookupError:
            return None
    try:
        models = list(apps.get_app_config(app_label).get_models())
    except LookupError:
        return None
    if base is None:
        words = set(_words(_url_name(match)))
        candidates = [m for m in models if m._meta.model_name in words]
        return max(candidates, key=lambda m: len(m._meta.model_name)) if candidates else None
    base = base.replace('_', '')
    exact = [m for m in models if m._meta.model_name == base]
    if exact:
        return exact[0]
    ending = [m for m in models if m._meta.model_name.endswith(base)]
    return ending[0] if len(ending) == 1 else None


def object_label(obj):
    return f"{str(obj._meta.verbose_name).capitalize()} {obj}"[:255]


def target_for(match):
    """Names the records the URL points at: {"project_id": 59} -> "Project AD-2451"."""
    if not match or not match.kwargs:
        return ''
    app_label = (getattr(match.func, '__module__', '') or '').split('.')[0]
    labels = []
    for key, value in match.kwargs.items():
        if 'token' in key.lower() or not str(value).isdigit():
            continue
        model = _model_for_kwarg(app_label, key, match)
        if model is None:
            continue
        obj = model._default_manager.filter(pk=value).first()
        if obj is not None:
            labels.append(object_label(obj))
    return ' › '.join(labels)[:255]


def describe(request):
    """(title, target) for a request with no tracked record changes."""
    match = getattr(request, 'resolver_match', None)
    if match is None:
        # Refused before Django matched the URL (the per-software access middleware).
        try:
            match = resolve(request.path_info)
        except Resolver404:
            match = None
    if not match:
        return request.path_info[:255], ''
    title = phrase_for(match, request.method)
    if not title:  # e.g. "forum-home": nothing left after the software name
        app = resolve_app(request.path_info)
        title = f"Opened {app}" if request.method in ('GET', 'HEAD') else request.path_info
    try:
        target = target_for(match)
    except Exception:
        logger.exception('Could not name the records for %s', request.path_info)
        target = ''
    return title[:255], target


def denied_title(title):
    """"Opened project" -> "Access denied: project"."""
    page = title[len('Opened '):] if title.startswith('Opened ') else title
    return 'Access denied' + (f": {page}" if page else '')


# --- Field-level changes ---------------------------------------------------------------

def is_tracked(model):
    meta = model._meta
    return (
        meta.app_label in TRACKED_APPS
        and not meta.model_name.endswith(_UNTRACKED_MODEL_SUFFIXES)
        and not meta.auto_created
    )


def _field_label(field):
    return str(field.verbose_name).capitalize()


def format_value(value, field=None):
    if value is None or value == '':
        return 'Empty'
    if field is not None and field.choices:
        value = dict(field.flatchoices).get(value, value)
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if hasattr(value, 'hour') and hasattr(value, 'tzinfo'):
        from django.utils import timezone
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime('%d %b %Y %H:%M')
    if hasattr(value, 'strftime'):
        return value.strftime('%d %b %Y')
    if hasattr(value, 'name') and hasattr(value, 'url'):  # FieldFile
        value = value.name or 'Empty'
    text = re.sub(r'<[^>]+>', ' ', str(value))  # rich-text fields
    text = re.sub(r'\s+', ' ', text).strip() or 'Empty'
    return text if len(text) <= MAX_VALUE_LENGTH else text[:MAX_VALUE_LENGTH - 1] + '…'


def _comparable_fields(instance, update_fields):
    for field in instance._meta.concrete_fields:
        if field.primary_key or field.name in _SKIPPED_FIELD_NAMES:
            continue
        if any(w in field.name.lower() for w in _SKIPPED_FIELD_WORDS):
            continue
        if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
            continue
        if update_fields is not None and field.name not in update_fields and field.attname not in update_fields:
            continue
        yield field


def field_changes(old, new, update_fields=None):
    changes = []
    for field in _comparable_fields(new, update_fields):
        before, after = getattr(old, field.attname), getattr(new, field.attname)
        if before == after:
            continue
        if field.is_relation:
            before = getattr(old, field.name) if before is not None else None
            after = getattr(new, field.name) if after is not None else None
        changes.append({
            'field': _field_label(field),
            'old': format_value(before, None if field.is_relation else field),
            'new': format_value(after, None if field.is_relation else field),
        })
    return changes


def title_for_changes(records):
    """Headline and event for the first record a request changed: "Project created",
    "Planned date changed", "Stage marked Completed", "Stage updated"."""
    first = records[0]
    kind = first['action']
    noun = first['model']
    if kind == 'create':
        return f"{noun} created", ActivityLog.Event.CREATE
    if kind == 'delete':
        return f"{noun} deleted", ActivityLog.Event.DELETE
    fields = first['fields']
    if len(fields) == 1:
        change = fields[0]
        if change['field'].lower() == 'status':
            return f"{noun} marked {change['new']}", ActivityLog.Event.UPDATE
        return f"{change['field']} changed", ActivityLog.Event.UPDATE
    return f"{noun} updated", ActivityLog.Event.UPDATE


# --- Writing ---------------------------------------------------------------------------

def record_event(event, request=None, user=None, username='', description='', status_code=None,
                 target='', changes=None):
    """Writes one log row. Never raises: logging must not be able to break a request."""
    try:
        if user is not None and not getattr(user, 'is_authenticated', False):
            user = None
        username = (username or (user.get_username() if user else ''))[:150]
        entry = ActivityLog(
            event=event,
            user=user,
            username=username,
            full_name=full_name_for(user, username)[:150],
            description=description[:255],
            target=target[:255],
            changes=changes or [],
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
