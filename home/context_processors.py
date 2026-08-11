from django.utils.functional import SimpleLazyObject


def kb_notifications(request):
    """
    Unread KB-notification count for the navbar bell, available on every
    template (base_forum.html is the only one that actually reads it).
    Wrapped in SimpleLazyObject so the count query only runs on pages that
    render the variable -- this processor is registered globally, so without
    the laziness every page in the whole app (tracker, inventory, etc.)
    would pay for a query it never uses.
    """
    if not request.user.is_authenticated:
        return {}

    def _count():
        from .models import Notification
        return Notification.objects.filter(recipient=request.user, is_read=False).count()

    return {'kb_unread_notifications': SimpleLazyObject(_count)}
