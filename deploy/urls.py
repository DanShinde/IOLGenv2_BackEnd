"""URL for the GitHub deploy webhook. Included from IOLGenv2_BackEnd/urls.py."""

from django.urls import path

from . import views

app_name = "deploy"

urlpatterns = [
    path("", views.github_webhook, name="github_webhook"),
]
