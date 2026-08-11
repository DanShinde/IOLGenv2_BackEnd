from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import api

router = DefaultRouter()
router.register(r'items', api.ItemViewSet, basename='api-item')
router.register(r'assignments', api.AssignmentViewSet, basename='api-assignment')
router.register(r'dispatches', api.DispatchViewSet, basename='api-dispatch')
router.register(r'history', api.HistoryViewSet, basename='api-history')
router.register(r'reservations', api.ReservationViewSet, basename='api-reservation')

urlpatterns = [
    # REST API
    path('api/', include(router.urls)),


    # Dashboard
    path('', views.dashboard, name='inventory-dashboard'),

    # Items Management
    path('items/', views.item_list, name='inventory-item-list'),
    path('items/add/', views.item_create, name='inventory-item-create'),
    path('items/<int:pk>/', views.item_detail, name='inventory-item-detail'),
    path('items/<int:pk>/edit/', views.item_update, name='inventory-item-update'),

    # Returns
    path('assignments/<int:pk>/return/', views.return_assignment, name='inventory-return-assignment'),
    path('dispatches/<int:pk>/return/', views.return_dispatch, name='inventory-return-dispatch'),

    # Transfers
    path('transfer/', views.transfer_item, name='inventory-transfer-item'),
    path('assign/', views.assign_item, name='inventory-assign-create'),
    path('dispatch/', views.dispatch_item, name='inventory-dispatch-create'),

    # Users
    path('users/', views.user_list, name='inventory-user-list'),
    path('users/<int:pk>/', views.user_detail, name='inventory-user-detail'),

    # Reservations
    path('reservations/', views.reservation_list, name='inventory-reservation-list'),
    path('reservations/add/', views.reservation_create, name='inventory-reservation-create'),
    path('reservations/<int:pk>/cancel/', views.reservation_cancel, name='inventory-reservation-cancel'),
    path('reservations/<int:pk>/fulfill/', views.reservation_fulfill, name='inventory-reservation-fulfill'),

    # History & Audit
    path('history/', views.history_list, name='inventory-history-list'),

    # Reports & Analytics
    path('reports/', views.reports, name='inventory-reports'),
    path('reports/export/', views.export_reports_excel, name='inventory-export-reports'),
    path('notifications/send/', views.send_notifications_now, name='inventory-send-notifications'),

    # Export Endpoints
    path('export/items/', views.export_items_csv, name='inventory-export-items'),
    path('export/history/', views.export_history_csv, name='inventory-export-history'),

    # AJAX Endpoints
    path('ajax/search/', views.ajax_search_items, name='inventory-ajax-search'),
    path('ajax/bulk-update/', views.bulk_update_items, name='inventory-bulk-update'),
]