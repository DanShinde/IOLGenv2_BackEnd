"""
REST API for the inventory app (JWT-authenticated, matching the rest of the project).

Item exposes full CRUD - it's a plain record with no side effects beyond the History
entries this module writes itself. Assignment/Dispatch/History are read-only here:
creating or ending one has multi-model side effects (item status/location, History)
that only make sense through the transfer/return workflow, so those stay web-only for
now rather than being duplicated as raw CRUD. Reservation supports create/list/retrieve
plus fulfill/cancel actions, which call the same services.py functions the HTML views use.
"""
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Item, Assignment, Dispatch, History, Reservation
from .serializers import (
    ItemSerializer, AssignmentSerializer, DispatchSerializer,
    HistorySerializer, ReservationSerializer,
)
from .views import invalidate_cache


class InventoryApiPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all().order_by('-created_at')
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InventoryApiPagination

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('item_type'):
            qs = qs.filter(item_type=params['item_type'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        search = params.get('search')
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(serial_number__icontains=search)
        return qs

    def perform_create(self, serializer):
        item = serializer.save(created_by=self.request.user)
        History.objects.create(
            item=item, action='ADDED', user=self.request.user,
            details=f'{item.get_item_type_display()} added to inventory with quantity {item.quantity}',
            location=item.location or 'Warehouse'
        )
        invalidate_cache('items_list')
        invalidate_cache('dashboard_stats')

    def perform_update(self, serializer):
        item = serializer.save()
        History.objects.create(
            item=item, action='UPDATED', user=self.request.user,
            details='Item details updated', location=item.location or 'Warehouse'
        )
        invalidate_cache('items_list')
        invalidate_cache('dashboard_stats')

    def perform_destroy(self, instance):
        raise serializers.ValidationError(
            'Deleting items via the API is not supported (it would cascade-delete the '
            'audit trail). Retire the item instead.'
        )


class AssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Assignment.objects.select_related('item', 'assigned_to', 'assigned_by').all()
    serializer_class = AssignmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InventoryApiPagination

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('active') == 'true':
            qs = qs.filter(return_date__isnull=True)
        return qs


class DispatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Dispatch.objects.select_related('item', 'dispatched_by').all()
    serializer_class = DispatchSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InventoryApiPagination

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('active') == 'true':
            qs = qs.filter(return_date__isnull=True)
        return qs


class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = History.objects.select_related('item', 'user').all()
    serializer_class = HistorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InventoryApiPagination

    def get_queryset(self):
        qs = super().get_queryset()
        item_id = self.request.query_params.get('item')
        if item_id:
            qs = qs.filter(item_id=item_id)
        return qs


class ReservationViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                          mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Reservation.objects.select_related('item', 'reserved_for', 'reserved_by').all()
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InventoryApiPagination

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        serializer.save(reserved_by=self.request.user)

    @action(detail=True, methods=['post'])
    def fulfill(self, request, pk=None):
        reservation = self.get_object()
        try:
            assignment = services.fulfill_reservation(reservation, performed_by=request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        invalidate_cache('items_list')
        invalidate_cache('dashboard_stats')
        return Response(AssignmentSerializer(assignment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        try:
            services.cancel_reservation(reservation)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ReservationSerializer(reservation).data, status=status.HTTP_200_OK)
