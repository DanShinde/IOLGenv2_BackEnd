from django.urls import path, include
from .views import home, downloads, clear_cache


urlpatterns = [
    path('', home, name='home'),
    path('downloads/', downloads, name='downloads'),
    path('cacheclear/', clear_cache, name='cache-clear'),
]
