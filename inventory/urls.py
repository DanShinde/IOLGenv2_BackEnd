from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='inventory-dashboard'),

    # Items Management
    path('items/', views.item_list, name='inventory-item-list'),
    path('items/add/', views.item_create, name='inventory-item-create'),
    path('items/<int:pk>/', views.item_detail, name='inventory-item-detail'),
    path('items/<int:pk>/edit/', views.item_update, name='inventory-item-update'),

    # Return Assignment (keep for returning items)
    path('assignments/<int:pk>/return/', views.return_assignment, name='inventory-return-assignment'),

    # Unified Transfers
    path('transfer/', views.transfer_item, name='inventory-transfer-item'),

    # History & Audit
    path('history/', views.history_list, name='inventory-history-list'),

    # Reports & Analytics
    path('reports/', views.reports, name='inventory-reports'),

    # Export Endpoints
    path('export/items/', views.export_items_csv, name='inventory-export-items'),
    path('export/history/', views.export_history_csv, name='inventory-export-history'),

    # AJAX Endpoints
    path('ajax/search/', views.ajax_search_items, name='inventory-ajax-search'),
    path('ajax/bulk-update/', views.bulk_update_items, name='inventory-bulk-update'),
]