from rest_framework.routers import DefaultRouter
from .views import (
    SegmentViewSet, PLCViewSet, IODeviceViewSet, ProjectViewSet,
    ModuleViewSet, IOListViewSet, SignalViewSet, ProjectReportViewSet, ExportIOListfromV1
)
from django.urls import path


router = DefaultRouter()
router.register(r'segments', SegmentViewSet)
router.register(r'plcs', PLCViewSet)
router.register(r'io-devices', IODeviceViewSet)
router.register(r'projects', ProjectViewSet)
router.register(r'project-reports', ProjectReportViewSet)
router.register(r'modules', ModuleViewSet)
router.register(r'iolists', IOListViewSet)
router.register(r'signals', SignalViewSet, basename='signals')

urlpatterns = router.urls

urlpatterns += [
    path('ExportIOListfromV1/<str:project_name>/', ExportIOListfromV1.as_view(), name='ExportIOListfromV1'),
]
