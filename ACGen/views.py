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
from django.core.cache import cache

_cache_timeout = 60 * 5  # Cache timeout (5 minutes)

# StandardString ViewSet
class StandardStringViewSet(viewsets.ModelViewSet):
    queryset = StandardString.objects.all()
    serializer_class = StandardStringSerializer
    permission_classes = [IsAuthenticated]  # Enforce JWT authentication

    def get_queryset(self):
        """
        Override to cache the StandardString queryset and fetch from cache if available.
        """
        cache_key = "standard_string_queryset"
        cached_data = cache.get(cache_key)

        if cached_data:
            print("Cache HIT")  # Debugging cache behavior
            return cached_data

        queryset = StandardString.objects.all()

        # Cache the result for 5 minutes
        cache.set(cache_key, queryset, timeout=86400)
        print("Cache MISS")  # Debugging cache behavior

        return queryset
    

class ClusterTemplateViewSet(viewsets.ModelViewSet):
    queryset = ClusterTemplate.objects.all()
    serializer_class = ClusterTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_cache_key(self, segment=None):
        """Generate a cache key based on the segment parameter."""
        return f"cluster_templates:{segment if segment else 'all'}"
    
    def perform_create(self, serializer):
        # Use the full name of the authenticated user
        full_name = self.request.user.get_full_name()
        # Invalidate the cache for the list
        cache.delete(self.get_cache_key())
        return serializer.save(uploaded_by=full_name, updated_by=full_name)

    def perform_update(self, serializer):
        # Use the full name of the authenticated user for updates
        full_name = self.request.user.get_full_name()
        # Invalidate the cache for the list
        # Invalidate cache for both list and specific instance
        instance = serializer.save(updated_by=full_name)
        cache.delete(self.get_cache_key())
        cache.delete(f"cluster_template:{instance.id}")

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
        cache_key = self.get_cache_key(segment)
        # Try to get the cached data
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        # If not cached, fetch from database
        queryset = self.queryset.filter(segment=segment) if segment else self.queryset.all()
        serializer = self.get_serializer(queryset, many=True)

        # Store in cache for 5 minutes (300 seconds)
        cache.set(cache_key, serializer.data, timeout=300)

        return Response(serializer.data)

# Parameter ViewSet

def deleteCachewithkeyStartPattern(key):
    """Delete all cache keys that start with 'cluster_template:'"""
    cache_keys = cache.get('all_cache_keys', set())

    # Filter and delete relevant keys
    keys_to_delete = [key for key in cache_keys if key.startswith(key)]
    
    for key in keys_to_delete:
        cache.delete(key)
    
    # Remove the deleted keys from tracking
    cache.set('all_cache_keys', cache_keys - set(keys_to_delete))

    return f"Deleted {len(keys_to_delete)} cache entries."



class ParameterViewSet(viewsets.ModelViewSet):
    queryset = Parameter.objects.all()
    serializer_class = ParameterSerializer
    cache_timeout = _cache_timeout

    def get_cache_key(self, id=None):
        """Generate a cache key based on the segment parameter."""
        return f"parameters:{id if id else 'all'}"


    def get_queryset(self):
        cluster_id = self.request.query_params.get('id', None)
        cache_key = self.get_cache_key(id)

        # Check if cached result exists
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data  # Return cached queryset

        # Compute queryset if not cached
        queryset = self.queryset.annotate(cluster_name=F("cluster__cluster_name"))
        if cluster_id:
            queryset = queryset.filter(cluster__id=cluster_id)

        # Cache the result
        cache.set(cache_key, queryset, self.cache_timeout)
        print('Cache-', cache.get(cache_key))
        return queryset

    def perform_create(self, serializer):
        full_name = self.request.user.get_full_name()
        serializer.save(uploaded_by=full_name, updated_by=full_name)
        self.invalidate_cache()

    def perform_update(self, serializer):
        full_name = self.request.user.get_full_name()
        serializer.save(updated_by=full_name)
        self.invalidate_cache()

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        self.invalidate_cache()
        return response

    def list(self, request, *args, **kwargs):
        
        queryset = self.get_queryset()
        if not queryset.exists():
            return Response({"detail": "No parameters found for the specified cluster name."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(queryset, many=True)
        cluster_name = queryset.first().cluster.cluster_name if queryset else None

        response_data = {
            "cluster_name": cluster_name,
            "parameters": serializer.data,
        }
        return Response(response_data)

    def invalidate_cache(self):
        """Delete all cache keys related to ParameterViewSet."""
        deleteCachewithkeyStartPattern("parameters:")
        

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



