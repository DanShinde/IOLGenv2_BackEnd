# IOLGenv2_BackEnd/middleware.py

from django.shortcuts import redirect
from accounts.models import UserProfile

from .access import access_denied

class TrackerGroupRequiredMiddleware:
    """
    Blocks any URL under /tracker/ unless the user is authenticated
    and belongs to the 'Trackers' group.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Adjust this prefix if your tracker URLs are mounted elsewhere
        if request.path_info.startswith('/tracker/'):
            # ✅ Allow public access to specific paths (Guest Access for Email Links)
            if request.path_info.startswith('/tracker/public/'):
                return self.get_response(request)

            # not logged in → send to login
            if not request.user.is_authenticated:
                return redirect('loginw')  
            # logged in but not in Trackers group → 403
            userprofile = UserProfile.objects.filter(user=request.user).first()
            if userprofile and not userprofile.is_tracker:
                return access_denied(request, 'Tracker', how_to_get='tick “Is tracker” on your user profile')
            # if not request.user.groups.filter(name='Trackers').exists():
            #     return HttpResponseForbidden("Access denied. User Not in Trackers group.")
        return self.get_response(request)

class PlannerAuthRequiredMiddleware:
    """
    Blocks any URL under /planner/ unless the user is authenticated.
    Redirects unauthenticated users to 'loginw'.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Adjust this prefix if your planner URLs are mounted elsewhere
        if request.path_info.startswith('/planner/'):
            if not request.user.is_authenticated:
                return redirect('loginw')
        return self.get_response(request)

class TestVaultAuthRequiredMiddleware:
    """
    Blocks any URL under /testvault/ unless the user is authenticated.
    Redirects unauthenticated users to 'loginw'.

    Exempts the shareable read-only report page and the two endpoints it depends on
    (report data lookup, live test-case generation) -- these back the "Share Report" /
    "Shareable View-Only Link" feature, which is meant to be sent to people (customers,
    external validators) who don't have a login, mirroring /tracker/public/.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith('/testvault/'):
            public_prefixes = (
                '/testvault/report/',
                '/testvault/api/report/data/',
                '/testvault/api/generate-test-cases/',
            )
            if request.path_info.startswith(public_prefixes):
                return self.get_response(request)

            if not request.user.is_authenticated:
                return redirect('loginw')
        return self.get_response(request)

class EstimatorGroupRequiredMiddleware:
    """
    Blocks any URL under /estimator/ unless the user is authenticated
    and their profile is flagged for Estimator access.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith('/estimator/'):
            if not request.user.is_authenticated:
                return redirect('loginw')
            userprofile = UserProfile.objects.filter(user=request.user).first()
            if userprofile and not userprofile.is_estimator:
                return access_denied(request, 'Estimator', how_to_get='tick “Is estimator” on your user profile')
        return self.get_response(request)

class KnowledgeBaseGroupRequiredMiddleware:
    """
    Blocks any URL under /forum/ (the Knowledge Base) unless the user is
    authenticated and either staff or a member of the 'Knowledge Base' group.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith('/forum/'):
            if not request.user.is_authenticated:
                return redirect('loginw')
            if not (request.user.is_staff or request.user.groups.filter(name='Knowledge Base').exists()):
                return access_denied(request, 'Knowledge Base', how_to_get='add you to the “Knowledge Base” group')
        return self.get_response(request)

class SkillGapGroupRequiredMiddleware:
    """
    Blocks any URL under /skillgap/ unless the user is authenticated
    and their profile is flagged for Skill Gap Analyzer access.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith('/skillgap/'):
            if not request.user.is_authenticated:
                return redirect('loginw')
            userprofile = UserProfile.objects.filter(user=request.user).first()
            if userprofile and not userprofile.is_skillgap:
                return access_denied(request, 'Skill Gap', how_to_get='tick “Is skillgap” on your user profile')
        return self.get_response(request)