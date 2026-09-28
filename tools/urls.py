from django.urls import path

from . import views

# No app_name / namespace: this project uses flat, globally unique URL names prefixed
# with the software name (estimator_*, skillgap_*), and activitylog/services.py reads
# that prefix to work out which software a log entry belongs to.
urlpatterns = [
    path('', views.tools_home, name='tools_home'),
    path('text-list/', views.textlist_view, name='tools_textlist'),
    path('text-list/download/', views.textlist_download, name='tools_textlist_download'),
    path('scl-io-mapping/', views.scl_view, name='tools_scl'),
    path('scl-io-mapping/download/', views.scl_download, name='tools_scl_download'),
]
