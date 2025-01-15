from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import StandardString, ClusterTemplate, Parameter
from .serializers import (
    StandardStringSerializer,
    ClusterTemplateSerializer,
    ParameterSerializer,
)

# StandardString ViewSet
class StandardStringViewSet(viewsets.ModelViewSet):
    queryset = StandardString.objects.all()
    serializer_class = StandardStringSerializer
    permission_classes = [IsAuthenticated]  # Enforce JWT authentication

# ClusterTemplate ViewSet
class ClusterTemplateViewSet(viewsets.ModelViewSet):
    queryset = ClusterTemplate.objects.all()
    serializer_class = ClusterTemplateSerializer
    permission_classes = [IsAuthenticated]  # Enforce JWT authentication

# Parameter ViewSet
class ParameterViewSet(viewsets.ModelViewSet):
    queryset = Parameter.objects.all()
    serializer_class = ParameterSerializer
    permission_classes = [IsAuthenticated]  # Enforce JWT authentication
