from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StandardStringViewSet, ClusterTemplateViewSet, ParameterViewSet

router = DefaultRouter()
router.register(r'standard-strings', StandardStringViewSet, basename='standardstring')
router.register(r'cluster-templates', ClusterTemplateViewSet, basename='clustertemplate')
router.register(r'parameters', ParameterViewSet, basename='parameter')

urlpatterns = [
    path('', include(router.urls)),
]
