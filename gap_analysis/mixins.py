from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied

from .models import user_can_manage_employee


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts a view to staff users; login is enforced separately by LoginRequiredMixin."""

    def test_func(self):
        return self.request.user.is_staff


class EmployeeSelfOrManagerRequiredMixin:
    """Restricts a per-employee DetailView (self.get_object() returns a SkillMatrix) to
    whoever is already allowed to see that one employee's skill data: staff, that employee's
    manager, or the employee viewing their own record. Reuses user_can_manage_employee() --
    the same rule that already gates who can set/approve that employee's skill ratings --
    rather than a separate, potentially-divergent check for view access."""

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user
        if not (user_can_manage_employee(user, obj) or obj.user_id == user.id):
            raise PermissionDenied("You don't have access to this employee's profile.")
        return obj


class CancelUrlMixin:
    """Exposes this view's own success_url as `cancel_url` in the template context, so a
    Cancel button lands on the same page a successful save would -- both should be the one
    fixed, content-appropriate destination for this kind of record (e.g. Role Matrix after
    a Designation), regardless of which page the form happened to be opened from."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = self.get_success_url()
        return context
