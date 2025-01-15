from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from .models import Segment, PLC, IODevice, Project, Module, IOList, Signal, ProjectReport
from .serializers import (
    SegmentSerializer, PLCSerializer, IODeviceSerializer, ProjectSerializer,
    ModuleSerializer, IOListSerializer, SignalSerializer, ProjectReportSerializer
)

class SegmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = Segment.objects.all()
    serializer_class = SegmentSerializer

class PLCViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = PLC.objects.all()
    serializer_class = PLCSerializer

class IODeviceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = IODevice.objects.all()
    serializer_class = IODeviceSerializer

class ProjectViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

class ProjectReportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = ProjectReport.objects.all()
    serializer_class = ProjectReportSerializer

class ModuleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer

class IOListViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = IOList.objects.all()
    serializer_class = IOListSerializer
    

class SignalViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = Signal.objects.all()
    serializer_class = SignalSerializer
