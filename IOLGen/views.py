from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from rest_framework.response import Response
from .models import Segment, PLC, IODevice, Project, Module, IOList, Signal, ProjectReport
from .serializers import (
    SegmentSerializer, PLCSerializer, IODeviceSerializer, ProjectSerializer,
    ModuleSerializer, IOListSerializer, SignalSerializer, ProjectReportSerializer
)
from rest_framework.exceptions import PermissionDenied

class SegmentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Segment.objects.all()
    serializer_class = SegmentSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        segment_names = queryset.values_list('name', flat=True)
        return Response(segment_names)

class PLCViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = PLC.objects.all()
    serializer_class = PLCSerializer

class IODeviceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = IODevice.objects.all()
    serializer_class = IODeviceSerializer

class ProjectViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

class IOListViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = IOList.objects.select_related('project').all()
    serializer_class = IOListSerializer
    

class ProjectReportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = ProjectReport.objects.all()
    serializer_class = ProjectReportSerializer

class ModuleViewSet(viewsets.ModelViewSet):
    # permission_classes = [IsAuthenticated]  # Require authentication
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

    def perform_create(self, serializer):
        # Only allow users in 'Managers' or 'SegmentSMEs' group to add
        if not self.request.user.groups.filter(name__in=['Managers', 'SegmentSMEs']).exists():
            raise PermissionDenied("You do not have permission to add this module.")
        serializer.save()

    def perform_destroy(self, instance):
        # Only allow users in 'Managers' or 'SegmentSMEs' group to delete
        if not self.request.user.groups.filter(name__in=['Managers', 'SegmentSMEs']).exists():
            raise PermissionDenied("You do not have permission to delete this module.")
        instance.delete()


class SignalViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    serializer_class = SignalSerializer
    queryset = Module.objects.none()  # Default queryset to satisfy DRF

    def get_queryset(self):
        """
        This view should return a list of all the signals
        for the module specified by the `module_id` parameter.
        """
        module_id = self.request.query_params.get('module_id', None)
        if module_id is not None:
            return Signal.objects.filter(module_id=module_id).select_related('module')
        return Signal.objects.select_related('module').all()
    
    def perform_create(self, serializer):
        # Only allow users in 'Managers' or 'SegmentSMEs' group to add
        if not self.request.user.groups.filter(name__in=['Managers', 'SegmentSMEs']).exists():
            raise PermissionDenied("You do not have permission to add this signal.")
        serializer.save()

    def perform_destroy(self, instance):
        # Only allow users in 'Managers' or 'SegmentSMEs' group to delete
        if not self.request.user.groups.filter(name__in=['Managers', 'SegmentSMEs']).exists():
            raise PermissionDenied("You do not have permission to delete this signal.")
        instance.delete()




