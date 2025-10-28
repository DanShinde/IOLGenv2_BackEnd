from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StandardStringViewSet,
    ClusterTemplateViewSet,
    ParameterViewSet,
    ParameterBulkViewSet,
    DashboardView,
    GenerationLogCreateView,
    ControlLibraryViewSet,
    bug_report_dashboard,
    update_bug_report_status,
    bulk_update_parameters,
    set_cluster_dependencies,
)
router = DefaultRouter()
router.register(r'standard-strings', StandardStringViewSet, basename='standardstring')
router.register(r'cluster-templates', ClusterTemplateViewSet, basename='clustertemplate')
router.register(r'parameters', ParameterViewSet, basename='parameter')
# router.register(r'parametersbulk', ParameterBulkViewSet, basename='parameterbulk')
router.register(r'control-libraries',ControlLibraryViewSet, basename='controllibrary')



urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', DashboardView, name='dashboard'),
    path('generation-logs/', GenerationLogCreateView.as_view(), name='create-generation-log'),
    path('parametersbulk/', ParameterBulkViewSet.as_view({
        'get': 'list',
        'post': 'create', 
        'put': 'bulk_update'  # Maps PUT to your bulk_update method
    })),
    path('bulk_update_parameters/', bulk_update_parameters, name='bulk-update-parameters'),
    path('set_cluster_dependencies/', set_cluster_dependencies, name='set-cluster-dependencies'),
    path('bug-reports/', bug_report_dashboard, name='bug-report-dashboard'),
    path('bug-reports/<int:pk>/update-status/', update_bug_report_status, name='bug-report-update-status'),
]
