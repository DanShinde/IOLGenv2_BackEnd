from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Items Management
    path('items/', views.item_list, name='item-list'),
    path('items/add/', views.item_create, name='item-create'),
    path('items/<int:pk>/', views.item_detail, name='item-detail'),
    path('items/<int:pk>/edit/', views.item_update, name='item-update'),
    
    # Return Assignment (keep for returning items)
    path('assignments/<int:pk>/return/', views.return_assignment, name='return-assignment'),
    
    
    # Unified Transfers
    path('transfer/', views.transfer_item, name='transfer-item'),
    
    # History & Audit
    path('history/', views.history_list, name='history-list'),
    
    # Reports & Analytics
    path('reports/', views.reports, name='reports'),
]