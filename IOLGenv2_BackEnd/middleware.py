# IOLGenv2_BackEnd/middleware.py

from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from accounts.models import UserProfile 

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
            # not logged in → send to login
            if not request.user.is_authenticated:
                return redirect('loginw')  
            # logged in but not in Trackers group → 403
            userprofile = UserProfile.objects.filter(user=request.user).first()
            try :
                if userprofile and not userprofile.is_tracker:
                    return HttpResponseForbidden("Access denied. User Not a Tracker.")
            except UserProfile.DoesNotExist:
                return HttpResponseForbidden("Access denied. User Profile Not Found.")
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