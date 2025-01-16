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
    serializer_class = ModuleSerializer
    queryset = Module.objects.none()  # Default queryset to satisfy DRF

    def get_queryset(self):
        """
        Limit the queryset to modules associated with the user's assigned segments.
        """
        user = self.request.user

        if hasattr(user, "profile"):
            # Get the segments assigned to the user's profile
            user_segments = user.profile.segments.all()
            return Module.objects.filter(segment__in=user_segments)

        # If the user doesn't have a profile, return an empty queryset
        return Module.objects.none()

class IOListViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = IOList.objects.all()
    serializer_class = IOListSerializer
    

class SignalViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = Signal.objects.all()
    serializer_class = SignalSerializer
