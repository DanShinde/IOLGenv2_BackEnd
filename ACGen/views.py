from django.dispatch import receiver
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from rest_framework import viewsets, generics, status
from rest_framework.permissions import IsAuthenticated
from .models import StandardString, ClusterTemplate, Parameter, GenerationLog
from .serializers import (
    StandardStringSerializer,
    ClusterTemplateSerializer,
    ParameterSerializer,
    GenerationLogSerializer,
    ControlLibrarySerializer

)
from rest_framework.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from rest_framework.response import Response
from rest_framework.decorators import action, permission_classes
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.db.models import Count
from rest_framework.decorators import api_view
from accounts.models import clear_info_cache
from .models import ControlLibrary
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
import json
# from django.db.models import ArrayAgg
from django.contrib.postgres.aggregates import ArrayAgg


_cache_timeout = 60 * 5  # Cache timeout (5 minutes)

class ControlLibraryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = ControlLibrary.objects.all()
    serializer_class = ControlLibrarySerializer

    # def list(self, request, *args, **kwargs):
    #     queryset = self.get_queryset()
    #     control_libraries = queryset.values_list('name', flat=True)
    #     return Response(control_libraries)


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

    def get_cache_key(self, **filters):
        """Generate cache key based on all filter parameters with versioning"""
        filter_parts = []
        for key, value in sorted(filters.items()):
            if value is not None:
                filter_parts.append(f"{key}:{value}")
        
        filter_string = "_".join(filter_parts) if filter_parts else "all"
        
        # Include version for automatic invalidation
        version = cache.get("cluster_templates_version", 0)
        return f"cluster_templates:v{version}:{filter_string}"

    def get_instance_cache_key(self, instance_id):
        return f"cluster_template:{instance_id}"

    def get_filter_params(self):
        """Extract and return all supported filter parameters"""
        return {
            'segment': self.request.query_params.get('segment'),
            'control_library': self.request.query_params.get('control_library'),
            'block_type': self.request.query_params.get('block_type'),
            # Add more filter parameters as needed
        }

    def get_queryset(self):
        filter_params = self.get_filter_params()
        cache_key = self.get_cache_key(**filter_params)
        cached_ids = cache.get(cache_key)

        if cached_ids:
            print("Cache HIT")
            return ClusterTemplate.objects.filter(pk__in=cached_ids).distinct().order_by('cluster_name')

        # Build queryset with filters
        queryset = self.queryset.all()
        
        # Apply filters dynamically
        for param, value in filter_params.items():
            if value is not None:
                queryset = queryset.filter(**{param: value})
        
        queryset = queryset.order_by('cluster_name')
        # queryset_ids = list(queryset.values_list('id', flat=True))

        queryset_ids = list(queryset.values_list('id', flat=True).distinct())
        cache.set(cache_key, queryset_ids, self.cache_timeout)
        # cache.set(cache_key, queryset_ids, self.cache_timeout)
        print("Cache MISS")
        return queryset

    def get_serializer(self, *args, **kwargs):
        """Override to handle compact parameter"""
        compact = self.request.query_params.get('compact', '').lower() == 'true'
        
        if compact:
            # Use a custom serializer for compact response or limit fields
            kwargs['fields'] = ['id','cluster_name', 'cluster_path', 'block_type', 'cluster_config', 'dependencies']
            
        return super().get_serializer(*args, **kwargs)

    def perform_create(self, serializer):
        full_name = self.request.user.get_full_name()
        instance = serializer.save(uploaded_by=full_name, updated_by=full_name)
        self.invalidate_all_cache()
        return instance

    def perform_update(self, serializer):
        full_name = self.request.user.get_full_name()
        instance = serializer.save(updated_by=full_name)
        self.invalidate_all_cache()
        self.invalidate_instance_cache(instance.id)
        return instance

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        self.invalidate_all_cache()
        self.invalidate_instance_cache(instance.id)
        return response

    def list(self, request, *args, **kwargs):
        filter_params = self.get_filter_params()
        compact = request.query_params.get('compact', '').lower() == 'true'
        
        cache_key = self.get_cache_key(**filter_params)
        cached_ids = cache.get(cache_key)

        if cached_ids:
            queryset = ClusterTemplate.objects.filter(pk__in=cached_ids).distinct().order_by('cluster_name')
        else:
            queryset = self.get_queryset()
            # Cache the list of IDs
            cache.set(cache_key, list(queryset.values_list('id', flat=True)), self.cache_timeout)

        # Handle compact response
        if compact:
            # Option 1: Use values() for efficiency (database level filtering)
            compact_data = queryset.distinct().values(
                'id',
                'cluster_name', 
                'cluster_path', 
                'block_type', 
                'cluster_config',
                'control_library'
                ).annotate(
                    dependencies=ArrayAgg('dependencies', distinct=True)
                )
            return Response(list(compact_data))
        else:
            # Standard serialization
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

    def invalidate_all_cache(self):
        """Efficiently invalidate cache using pattern matching or cache versioning"""
        # Option 1: Simple approach - clear all cluster template caches
        # This is much faster than querying for all possible combinations
        
        # If using Redis, you could use pattern-based deletion:
        # cache.delete_pattern("cluster_templates:*")
        
        # For Django's default cache, use a simple version-based approach:
        cache_version_key = "cluster_templates_version"
        current_version = cache.get(cache_version_key, 0)
        cache.set(cache_version_key, current_version + 1, None)  # Never expires
        
        # Alternative: Delete only the most common cache keys without DB queries
        common_cache_keys = [
            self.get_cache_key(),  # all items
            # Add more specific keys if you know common patterns
        ]
        cache.delete_many(common_cache_keys)

    def invalidate_instance_cache(self, instance_id):
        """Invalidate cache for specific instance"""
        cache.delete(self.get_instance_cache_key(instance_id))

    # Legacy method for backward compatibility
    def invalidate_cache(self, instance_id=None):
        """Legacy method - redirects to new methods"""
        self.invalidate_all_cache()
        if instance_id:
            self.invalidate_instance_cache(instance_id)

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

    # @action(detail=False, methods=['put'])
    def bulk_update(self, request, *args, **kwargs):
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

                clear_info_cache("parameters", instance.cluster.id)
                return Response({'id': 'True'}, status=status.HTTP_200_OK)
            except ValidationError as e:
                return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)

    

class GenerationLogCreateView(generics.CreateAPIView):
    queryset = GenerationLog.objects.all()
    serializer_class = GenerationLogSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        full_name = self.request.user.get_full_name() or self.request.user.username
        serializer.save(user=full_name)



@api_view(["GET"])
def DashboardView(request):
    # Query: Count of clusters per segment
    segment_counts = ClusterTemplate.objects.values("segment").annotate(segment_count=Count("segment")).order_by("-segment_count")

    # Formatting data for JSON response
    data = [{"segment": item["segment"], "count": item["segment_count"]} for item in segment_counts]

    return Response(data)





@csrf_exempt  # Remove this if you want CSRF protection
@require_http_methods(["POST"])
@permission_classes([IsAuthenticated])
def bulk_update_parameters(request):
    """Handle bulk update of assignment_value with atomic transactions."""
    
    try:
        # Parse JSON data
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON data"}, 
            status=400
        )

    if not isinstance(data, list):
        return JsonResponse(
            {"error": "Expected a list of entries."}, 
            status=400
        )

    # Get user info (adjust based on your auth setup)
    full_name = request.user.get_full_name() if request.user.is_authenticated else "Anonymous"
    
    with transaction.atomic():
        try:
            for entry in data:
                if "id" not in entry or "assignment_value" not in entry:
                    return JsonResponse(
                        {"error": "Each entry must include 'id' and 'assignment_value'."}, 
                        status=400
                    )

                # Get the parameter instance
                try:
                    instance = Parameter.objects.select_related('cluster').get(id=entry["id"])
                except Parameter.DoesNotExist:
                    return JsonResponse(
                        {"error": f"Parameter with id {entry['id']} not found."}, 
                        status=400
                    )

                # Update the instance
                instance.assignment_value = entry["assignment_value"]
                instance.updated_by = full_name
                instance.save()

                # Clear cache (adjust based on your cache setup)
                clear_info_cache("parameters", instance.cluster.id)

            return JsonResponse({'success': True}, status=200)

        except Exception as e:
            return JsonResponse(
                {"error": str(e)}, 
                status=400
            )





def check_circular_dependency(cluster, new_dependency):
    """Check if adding new_dependency would create a circular dependency"""
    def has_path_to(from_cluster, to_cluster, visited=None):
        if visited is None:
            visited = set()
        
        if from_cluster.id in visited or from_cluster.id == to_cluster.id:
            return from_cluster.id == to_cluster.id
            
        visited.add(from_cluster.id)
        
        for dep in from_cluster.dependencies.all():
            if has_path_to(dep, to_cluster, visited.copy()):
                return True
                
        return False
    
    return has_path_to(new_dependency, cluster)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_cluster_dependencies(request):
    """
    Set dependencies for a cluster
    POST /api/set-dependencies/
    Body: {
        "cluster_id": 1,
        "dependency_ids": [2, 3, 4]
    }
    """
    cluster_id = request.data.get('cluster_id')
    dependency_ids = request.data.get('dependency_ids', [])
    
    if not cluster_id:
        return Response({'error': 'cluster_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        cluster = get_object_or_404(ClusterTemplate, id=cluster_id)
        
        # Remove self-reference if present
        dependency_ids = [dep_id for dep_id in dependency_ids if dep_id != cluster_id]
        
        # Get dependencies
        dependencies = ClusterTemplate.objects.filter(id__in=dependency_ids)
        
        # Check for circular dependencies
        for dependency in dependencies:
            if check_circular_dependency(cluster, dependency):
                return Response(
                    {'error': f'Circular dependency detected with {dependency.cluster_name}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Set dependencies
        cluster.dependencies.set(dependencies)
        
        # Clear cache
        cache.delete("cluster_templates:all")
        cache.delete(f"cluster_template:{cluster_id}")
        
        return Response({
            'success': True,
            'message': 'Dependencies updated successfully',
            'cluster_id': cluster_id,
            'dependency_count': len(dependencies)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"Error setting dependencies: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)