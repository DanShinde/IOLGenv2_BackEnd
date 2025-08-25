from django.http import JsonResponse
from django.shortcuts import render
from accounts.models import Info
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.core.cache import cache


@login_required
def home(request):
    return render(request, 'base.html')


@login_required
def downloads(request):
    infos = Info.objects.all()
    context = {
        'infos': infos
    }
    return render(request, 'home/downloads.html', context)


from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied

def superuser_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view

@superuser_required
def clear_cache(request):
    cache.clear()
    return JsonResponse({"status": "ok", "message": "Cache cleared"})