from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import StandardString, ClusterTemplate, Parameter
from .serializers import (
    StandardStringSerializer,
    ClusterTemplateSerializer,
    ParameterSerializer,
)

from rest_framework.response import Response
from rest_framework import status

# StandardString ViewSet
class StandardStringViewSet(viewsets.ModelViewSet):
    queryset = StandardString.objects.all()
    serializer_class = StandardStringSerializer
    permission_classes = [IsAuthenticated]  # Enforce JWT authentication


class ClusterTemplateViewSet(viewsets.ModelViewSet):
    queryset = ClusterTemplate.objects.all()
    serializer_class = ClusterTemplateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Use the full name of the authenticated user
        full_name = self.request.user.get_full_name()
        return serializer.save(uploaded_by=full_name, updated_by=full_name)

    def perform_update(self, serializer):
        # Use the full name of the authenticated user for updates
        full_name = self.request.user.get_full_name()
        serializer.save(updated_by=full_name)

    def create(self, request, *args, **kwargs):
        # Handle requests with or without an ID
        data = request.data
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        return Response({"id": instance.cluster_id}, status=status.HTTP_201_CREATED)
    
    def list(self, request, *args, **kwargs):
        # Retrieve a list of ClusterTemplates and return only their names
        segment = request.query_params.get('segment', None)

        if segment:
            # Filter by segment if provided in query params
            queryset = self.queryset.filter(segment=segment)
        else:
            # If no segment is provided, return all ClusterTemplates
            queryset = self.queryset.all()

        # Extract only the cluster names
        # names = queryset.values_list('cluster_name', flat=True)
        # return Response(queryset)
        # Serialize the queryset to return all ClusterTemplate details
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

# Parameter ViewSet

class ParameterViewSet(viewsets.ModelViewSet):
    queryset = Parameter.objects.all()
    serializer_class = ParameterSerializer
    permission_classes = [IsAuthenticated]  # Enforce JWT authentication

    def get_queryset(self):
        # Get the cluster_id from the query parameters
        cluster_id = self.request.query_params.get('cluster_id', None)
        if cluster_id:
            # Filter parameters by the cluster_id
            return self.queryset.filter(cluster__cluster_id=cluster_id)
        return self.queryset

    def perform_create(self, serializer):
        # Use the full name of the authenticated user
        full_name = self.request.user.get_full_name()
        serializer.save(uploaded_by=full_name, updated_by=full_name)

    def perform_update(self, serializer):
        # Use the full name of the authenticated user for updates
        full_name = self.request.user.get_full_name()
        serializer.save(updated_by=full_name)

    def list(self, request, *args, **kwargs):
        """
        Optionally add a custom response for empty results.
        """
        queryset = self.get_queryset()
        if not queryset.exists():
            return Response(
                {"detail": "No parameters found for the specified cluster name."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

