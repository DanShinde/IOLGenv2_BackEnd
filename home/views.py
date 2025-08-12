from django.shortcuts import render
from accounts.models import Info
# Create your views here.
from django.contrib.auth.decorators import login_required


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