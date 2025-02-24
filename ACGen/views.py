from django.dispatch import receiver
from django.shortcuts import render
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
from rest_framework.decorators import action
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import viewsets, status
from django.db.models import Count
from rest_framework.decorators import api_view
from accounts.models import clear_info_cache

_cache_timeout = 60 * 5  # Cache timeout (5 minutes)

class StandardStringViewSet(viewsets.ModelViewSet):
    queryset = StandardString.objects.all()
    serializer_class = StandardStringSerializer
    permission_classes = [IsAuthenticated]
    cache_timeout = 86400  # 24 hours cache timeout

    def get_cache_key(self):
        return "standard_string_queryset"

    def get_queryset(self):
        cache_key = self.get_cache_key()
        cached_data = cache.get(cache_key)

        if cached_data:
            print("Cache HIT")
            return StandardString.objects.filter(pk__in=[obj.pk for obj in cached_data])

        queryset = self.queryset
        cache.set(cache_key, list(queryset), self.cache_timeout)
        print("Cache MISS")
        return queryset

    def perform_create(self, serializer):
        instance = serializer.save()
        self.invalidate_cache()
        return instance

    def perform_update(self, serializer):
        instance = serializer.save()
        self.invalidate_cache()
        return instance

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        self.invalidate_cache()
        return response

    def invalidate_cache(self):
        """Invalidate the StandardString cache."""
        cache.delete(self.get_cache_key())


class ClusterTemplateViewSet(viewsets.ModelViewSet):
    queryset = ClusterTemplate.objects.all()
    serializer_class = ClusterTemplateSerializer
    permission_classes = [IsAuthenticated]
    cache_timeout = 300  # 5 minutes cache timeout

    def get_cache_key(self, segment=None):
        return f"cluster_templates:{segment if segment else 'all'}"

    def get_instance_cache_key(self, instance_id):
        return f"cluster_template:{instance_id}"

    def get_queryset(self):
        segment = self.request.query_params.get('segment', None)
        cache_key = self.get_cache_key(segment)
        cached_ids = cache.get(cache_key)  # Expecting a list of IDs

        if cached_ids:
            print("Cache HIT")
            return ClusterTemplate.objects.filter(pk__in=cached_ids)

        queryset = self.queryset.filter(segment=segment).order_by('cluster_name') if segment else self.queryset.order_by('cluster_name')
        queryset_ids = list(queryset.values_list('id', flat=True))  # Store only IDs in cache

        cache.set(cache_key, queryset_ids, self.cache_timeout)
        print("Cache MISS")
        return queryset

    def perform_create(self, serializer):
        full_name = self.request.user.get_full_name()
        instance = serializer.save(uploaded_by=full_name, updated_by=full_name)
        self.invalidate_cache()
        return instance

    def perform_update(self, serializer):
        full_name = self.request.user.get_full_name()
        instance = serializer.save(updated_by=full_name)
        self.invalidate_cache(instance.id)
        return instance

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        self.invalidate_cache(instance.id)
        return response

    def list(self, request, *args, **kwargs):
        segment = request.query_params.get('segment', None)
        cache_key = self.get_cache_key(segment)
        cached_ids = cache.get(cache_key)

        if cached_ids:
            queryset = ClusterTemplate.objects.filter(pk__in=cached_ids)
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        # Cache the list of IDs instead of full objects
        cache.set(cache_key, list(queryset.values_list('id', flat=True)), self.cache_timeout)

        return Response(serializer.data)

    def invalidate_cache(self, instance_id=None):
        """Invalidate cache for all ClusterTemplate lists and specific instances."""
        cache.delete(self.get_cache_key())
        if instance_id:
            cache.delete(self.get_instance_cache_key(instance_id))


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
    queryset = Parameter.objects.select_related('cluster').all()
    serializer_class = ParameterSerializer
    cache_timeout = 60 * 15  # 15 minutes for cache
    permission_classes = [IsAuthenticated]

    def get_cache_key(self, id=None):
        """Generate a cache key based on the segment parameter."""
        return f"parameters:{id if id else 'all'}"

    def get_queryset(self):
        """Retrieve queryset with caching applied."""
        cluster_id = self.request.query_params.get("id", None)

        queryset = self.queryset.annotate(cluster_name=F("cluster__cluster_name"))
        if cluster_id:
            queryset = queryset.filter(cluster__id=cluster_id)

        # Store queryset in cache
        # cache.set(cache_key, queryset, self.cache_timeout)
        return queryset

    # @method_decorator(cache_page(60 * 15))  # Cache only GET requests
    def list(self, request, *args, **kwargs):
        cacheKey = self.get_cache_key(request.query_params.get("id"))
        data1 = cache.get(cacheKey)
        if data1:
            print(f"Cache HIT: {cacheKey}")
            return Response(data1)
        
        print(f"Cache MISS: {cacheKey}")
        
        queryset = self.get_queryset()
        if not queryset.exists():
            return Response({"detail": "No parameters found for the specified cluster name."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(queryset, many=True)
        cluster_name = queryset.first().cluster.cluster_name if queryset else None

        response_data = {
            "cluster_name": cluster_name,
            "parameters": serializer.data,
        }
        cache.set(cacheKey, response_data, self.cache_timeout)
        return Response(response_data)

    def perform_create(self, serializer):
        """Handle creation of a Parameter and invalidate cache."""
        full_name = self.request.user.get_full_name()
        serializer.save(uploaded_by=full_name, updated_by=full_name)
        self.invalidate_cache()

    def perform_update(self, serializer):
        """Handle update of a Parameter and invalidate cache."""
        full_name = self.request.user.get_full_name()
        serializer.save(updated_by=full_name)
        self.invalidate_cache()

    def destroy(self, request, *args, **kwargs):
        """Handle deletion of a Parameter and invalidate cache."""
        response = super().destroy(request, *args, **kwargs)
        self.invalidate_cache()
        return response

    def invalidate_cache(self):
        """Delete all cache keys related to ParameterViewSet."""
        print("Invalidating cache...")
        for key in cache._cache.keys():  # Works for LocMemCache
            if key.startswith("parameters:"):
                cache.delete(key)
        print("Cache invalidated successfully!")


class ParameterBulkViewSet(viewsets.ModelViewSet):
    queryset = Parameter.objects.select_related('cluster').all()
    serializer_class = ParameterSerializer
    cache_timeout = 60 * 15  # 15 minutes
    permission_classes = [IsAuthenticated]

    def get_cache_key(self, cluster_id=None, cluster_name=None):
        """Generate a cache key based on query parameters."""
        if cluster_id:
            return f"parameters:cluster_id:{cluster_id}"
        elif cluster_name:
            return f"parameters:cluster_name:{cluster_name}"
        return "parameters:all"

    def get_queryset(self):
        """Retrieve queryset with caching."""
        cluster_id = self.request.query_params.get("id", None)
        cluster_name = self.request.query_params.get("cluster_name", None)
        cache_key = self.get_cache_key(cluster_id, cluster_name)
        
        # Check cache
        cached_data = cache.get(cache_key)
        if cached_data:
            print(f"Cache HIT: {cache_key}")
            return cached_data  # Return cached queryset

        print(f"Cache MISS: {cache_key}")
        queryset = self.queryset.annotate(cluster_name=F("cluster__cluster_name"))
        if cluster_id:
            queryset = queryset.filter(cluster__id=cluster_id)
        elif cluster_name:
            queryset = queryset.filter(cluster__cluster_name=cluster_name)

        # Cache queryset
        cache.set(cache_key, queryset, self.cache_timeout)
        return queryset

    @method_decorator(cache_page(60 * 15))  # Cache only GET requests
    def list(self, request, *args, **kwargs):
        """List all parameters with caching."""
        queryset = self.get_queryset()
        if not queryset.exists():
            return Response(
                {"detail": "No parameters found for the specified criteria."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cluster_name = self.request.query_params.get("cluster_name", None)
        serializer = self.get_serializer(queryset, many=True)
        config = ClusterTemplate.objects.get(cluster_name=cluster_name).cluster_config if cluster_name else None
        if cluster_name:
            return Response({
                "cluster_name": cluster_name,
                "parameters": serializer.data,
                "cluster_config" : config
            })

        return Response(serializer.data)

    def perform_create(self, serializer):
        """Create a parameter and invalidate cache."""
        full_name = self.request.user.get_full_name()
        serializer.save(uploaded_by=full_name, updated_by=full_name)

    def perform_update(self, serializer):
        """Update a parameter and invalidate cache."""
        full_name = self.request.user.get_full_name()
        serializer.save(updated_by=full_name)

    def create(self, request, *args, **kwargs):
        """Handle bulk creation with atomic transactions."""
        data = request.data

        if not isinstance(data, list):
            return Response(
                {"error": "Expected a list of entries."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_name = request.user.get_full_name()
        serializers = []

        with transaction.atomic():
            try:
                for entry in data:
                    entry["uploaded_by"] = full_name
                    entry["updated_by"] = full_name

                    serializer = self.get_serializer(data=entry)
                    serializer.is_valid(raise_exception=True)
                    serializers.append(serializer)

                for serializer in serializers:
                    serializer.save()


                return Response(
                    [serializer.data for serializer in serializers],
                    status=status.HTTP_201_CREATED,
                )
            except ValidationError as e:
                return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, *args, **kwargs):
        """Handle bulk update of `assignment_value` with atomic transactions."""
        data = request.data

        if not isinstance(data, list):
            return Response(
                {"error": "Expected a list of entries."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_name = request.user.get_full_name()
        serializers = []

        with transaction.atomic():
            try:
                for entry in data:
                    if "id" not in entry or "assignment_value" not in entry:
                        raise ValidationError("Each entry must include 'id' and 'assignment_value'.")

                    instance = self.get_queryset().filter(id=entry["id"]).first()
                    if not instance:
                        raise ValidationError(f"Parameter with id {entry['id']} not found.")

                    entry["updated_by"] = full_name

                    serializer = self.get_serializer(instance, data=entry, partial=True)
                    serializer.is_valid(raise_exception=True)
                    serializers.append(serializer)

                for serializer in serializers:
                    serializer.save()

                clear_info_cache("parameters",instance.cluster.id)
                return Response({'id': 'True'}, status=status.HTTP_200_OK)
            except ValidationError as e:
                return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)




@api_view(["GET"])
def DashboardView(request):
    # Query: Count of clusters per segment
    segment_counts = ClusterTemplate.objects.values("segment").annotate(segment_count=Count("segment")).order_by("-segment_count")

    # Formatting data for JSON response
    data = [{"segment": item["segment"], "count": item["segment_count"]} for item in segment_counts]

    return Response(data)