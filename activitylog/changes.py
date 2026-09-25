"""Follows the records a change request saves, so its log entry can say what changed.

While ActivityLogMiddleware handles a POST/PUT/PATCH/DELETE it opens a collector. Model
signals then add one record per saved object: created, deleted, or updated with the fields
that changed and their old and new values. Outside a request (shell, management commands,
background jobs) nothing is collected and the signals return straight away.
"""
import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from .services import MAX_TRACKED_OBJECTS, field_changes, is_tracked, object_label

logger = logging.getLogger(__name__)

_collector = ContextVar('activitylog_collector', default=None)


class _Collector:
    def __init__(self):
        self.records = []
        self.by_key = {}
        self.old = {}       # id(instance) -> copy of the row before this save
        self.extra = 0      # objects saved after MAX_TRACKED_OBJECTS was reached

    def full(self):
        return len(self.records) >= MAX_TRACKED_OBJECTS

    def add(self, instance, action, fields=()):
        key = (instance._meta.label, instance.pk)
        existing = self.by_key.get(key)
        if existing is not None:
            # The same row saved twice: fold the second save into the first record.
            if existing['action'] == 'update' and action == 'update':
                known = {f['field']: f for f in existing['fields']}
                for f in fields:
                    if f['field'] in known:
                        known[f['field']]['new'] = f['new']
                    else:
                        existing['fields'].append(f)
            elif action == 'delete':
                existing['action'] = 'delete'
                existing['fields'] = []
            return
        if self.full():
            self.extra += 1
            return
        record = {
            'model': str(instance._meta.verbose_name).capitalize(),
            'object': object_label(instance),
            'action': action,
            'fields': list(fields),
        }
        self.records.append(record)
        self.by_key[key] = record


@contextmanager
def collect_changes():
    collector = _Collector()
    token = _collector.set(collector)
    try:
        yield collector.records
    finally:
        _collector.reset(token)
        # Drop updates where nothing visible changed (a save() with identical values).
        collector.records[:] = [r for r in collector.records if r['action'] != 'update' or r['fields']]
        if collector.extra:
            collector.records.append({'model': '', 'object': '', 'action': 'more',
                                      'fields': [], 'count': collector.extra})
        _put_primary_first(collector.records)


def _put_primary_first(records):
    """Deleting a record deletes its children first, so their signals arrive first. The
    record the person actually deleted is the last of that opening run of deletes."""
    if not records or records[0]['action'] != 'delete':
        return
    run = 0
    while run < len(records) and records[run]['action'] == 'delete':
        run += 1
    records.insert(0, records.pop(run - 1))


def _active(sender, raw=False):
    collector = _collector.get()
    if collector is None or raw or not is_tracked(sender):
        return None
    return collector


@receiver(pre_save, dispatch_uid='activitylog_pre_save')
def remember_old_row(sender, instance, raw=False, **kwargs):
    collector = _active(sender, raw)
    if collector is None or instance._state.adding or instance.pk is None or collector.full():
        return
    try:
        collector.old[id(instance)] = sender._base_manager.filter(pk=instance.pk).first()
    except Exception:
        logger.exception('Could not read the previous values of %s', sender.__name__)


@receiver(post_save, dispatch_uid='activitylog_post_save')
def record_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    collector = _active(sender, raw)
    if collector is None:
        return
    try:
        if created:
            collector.add(instance, 'create')
            return
        old = collector.old.pop(id(instance), None)
        if old is None:
            if collector.full():
                collector.extra += 1
            return
        collector.add(instance, 'update', field_changes(old, instance, update_fields))
    except Exception:
        logger.exception('Could not record the change to %s', sender.__name__)


@receiver(pre_delete, dispatch_uid='activitylog_pre_delete')
def record_delete(sender, instance, **kwargs):
    collector = _active(sender)
    if collector is None:
        return
    try:
        collector.add(instance, 'delete')
    except Exception:
        logger.exception('Could not record the deletion of %s', sender.__name__)
