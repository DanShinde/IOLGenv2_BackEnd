from django.contrib.auth.mixins import UserPassesTestMixin


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts a view to staff users; login is enforced separately by LoginRequiredMixin."""

    def test_func(self):
        return self.request.user.is_staff
