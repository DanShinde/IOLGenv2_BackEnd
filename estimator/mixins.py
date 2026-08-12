from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts a view to staff users (the "admin maintains activities/modules/matrix"
    tier); login is enforced separately by LoginRequiredMixin and the module-access
    middleware."""

    def test_func(self):
        return self.request.user.is_staff


class CancelUrlMixin:
    """Exposes this view's own success_url as `cancel_url` in the template context, so a
    Cancel button on the shared add_form.html lands on the same page a successful save
    would.

    Uses `self.success_url` directly rather than `self.get_success_url()`: the latter
    (ModelFormMixin) does `self.success_url.format(**self.object.__dict__)`, which blows
    up on a CreateView's GET request -- self.object is still None at that point, before
    anything has been saved."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = self.success_url
        return context


class ProtectedDeleteMixin:
    """Turns a ProtectedError (raised when deleting a record still referenced with
    on_delete=PROTECT elsewhere -- e.g. a Module Type used by a saved Project) into a
    friendly message + redirect instead of a 500."""

    protected_message = "Can't delete -- this record is still used by one or more projects."

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        label = str(self.object)
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(request, self.protected_message)
            return redirect(success_url)
        messages.success(request, f'"{label}" deleted.')
        return redirect(success_url)
