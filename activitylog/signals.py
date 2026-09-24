from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import ActivityLog
from .services import record_event


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record_event(ActivityLog.Event.LOGIN, request=request, user=user, description='Signed in')


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    # user is None when a session had already expired
    record_event(ActivityLog.Event.LOGOUT, request=request, user=user, description='Signed out')


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    # Only the attempted username is kept -- never the password that was tried.
    record_event(
        ActivityLog.Event.LOGIN_FAILED, request=request,
        username=str(credentials.get('username') or ''), description='Failed sign-in attempt',
    )
