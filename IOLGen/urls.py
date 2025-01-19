from rest_framework.routers import DefaultRouter
from .views import (
    SegmentViewSet, PLCViewSet, IODeviceViewSet, ProjectViewSet,
    ModuleViewSet, IOListViewSet, SignalViewSet, ProjectReportViewSet
)

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
