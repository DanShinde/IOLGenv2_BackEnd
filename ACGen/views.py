from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import StandardString, ClusterTemplate, Parameter
from .serializers import (
    StandardStringSerializer,
    ClusterTemplateSerializer,
    ParameterSerializer,
)
from rest_framework.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action

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
        return Response({"id": instance.id}, status=status.HTTP_201_CREATED)
    
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
    # permission_classes = [IsAuthenticated]  # Enforce JWT authentication

    def get_queryset(self):
        # Get the cluster_id from the query parameters
        cluster_id = self.request.query_params.get('id', None)
        if cluster_id:
            # Filter parameters by the cluster_id
            # return self.queryset.filter(cluster__cluster_id=cluster_id)
            return self.queryset.filter(cluster__id=cluster_id).annotate(cluster_name=F("cluster__cluster_name"))
        return self.queryset.annotate(cluster_name=F("cluster__cluster_name"))
        # return self.queryset

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
        # Include cluster name in the response
        cluster_name = None
        cluster_id = self.request.query_params.get("id", None)
        if cluster_id:
            cluster_name = queryset.first().cluster.cluster_name  # Assuming all rows share the same cluster

        response_data = {
            "cluster_name": cluster_name,
            "parameters": serializer.data,
        }
        return Response(response_data)



class ParameterBulkViewSet(viewsets.ModelViewSet):
    queryset = Parameter.objects.all()
    serializer_class = ParameterSerializer
    # permission_classes = [IsAuthenticated]  # Enforce JWT authentication

    def get_queryset(self):
        # Get the cluster_id from the query parameters
        cluster_id = self.request.query_params.get('id', None)
        cluster_name = self.request.query_params.get('cluster_name', None)
        if cluster_id:
            # Filter parameters by the cluster_id
            return self.queryset.filter(cluster__id=cluster_id)
        if cluster_name:
            # Filter parameters by the cluster_name
            return self.queryset.filter(cluster__cluster_name=cluster_name)
        return self.queryset

    def perform_create(self, serializer):
        # Use the full name of the authenticated user
        full_name = self.request.user.get_full_name()
        serializer.save(uploaded_by=full_name, updated_by=full_name)

    def perform_update(self, serializer):
        # Use the full name of the authenticated user for updates
        full_name = self.request.user.get_full_name()
        serializer.save(updated_by=full_name)

    def create(self, request, *args, **kwargs):
        """
        Overriding the create method to handle bulk creation.
        Ensures all entries are validated and commits only if all are valid.
        """
        data = request.data

        # Check if it's a list of entries
        if not isinstance(data, list):
            return Response(
                {"error": "Expected a list of entries."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_name = request.user.get_full_name()
        serializers = []
        
        # Start a database transaction
        with transaction.atomic():
            try:
                for entry in data:
                    # Add user-specific fields to each entry
                    entry["uploaded_by"] = full_name
                    entry["updated_by"] = full_name

                    # Validate each entry
                    serializer = self.get_serializer(data=entry)
                    serializer.is_valid(raise_exception=True)
                    serializers.append(serializer)

                # Save all entries only if they are all valid
                for serializer in serializers:
                    serializer.save()

                # Return the created entries
                return Response(
                    [serializer.data for serializer in serializers],
                    status=status.HTTP_201_CREATED,
                )
            except ValidationError as e:
                # Return validation errors if any entry is invalid
                return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, *args, **kwargs):
        """
        Handle PUT request for bulk update of 'assignment_value' with atomic transactions.
        """
        data = request.data
        # Check if it's a list of entries
        if not isinstance(data, list):
            return Response(
                {"error": "Expected a list of entries."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_name = request.user.get_full_name()
        serializers = []
        
        # Start a database transaction
        with transaction.atomic():
            try:
                for entry in data:
                    # Ensure that each entry has an 'id' field for update
                    if "id" not in entry or "assignment_value" not in entry:
                        raise ValidationError("Each entry must include 'id' and 'assignment_value'.")

                    # Get the existing parameter instance to update
                    instance = self.get_queryset().filter(id=entry["id"]).first()
                    if not instance:
                        raise ValidationError(f"Parameter with id {entry['id']} not found.")

                    # Only update the 'assignment_value' field
                    entry["updated_by"] = full_name

                    # Validate each entry
                    serializer = self.get_serializer(instance, data=entry, partial=True)
                    serializer.is_valid(raise_exception=True)
                    serializers.append(serializer)

                # Save all entries only if they are all valid
                for serializer in serializers:
                    serializer.save()

                # Return the updated entries
                return Response(
                    {'id': 'True'},
                    status=status.HTTP_200_OK,
                )
            except ValidationError as e:
                # Return validation errors if any entry is invalid
                return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)

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
        # If cluster_name is provided, modify the response format
        cluster_name = self.request.query_params.get('cluster_name', None)
        if cluster_name:
            return Response({
                "cluster_name": cluster_name,
                "parameters": serializer.data
            })
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)



