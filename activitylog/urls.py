from django.urls import path

from . import views

urlpatterns = [
    path('', views.log_list, name='activity_log'),
]
