# planner/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.project_list_view, name='planner_project_list'),
    path('planner/all/', views.consolidated_planner_view, name='planner_consolidated_planner'),
    path('planner/<int:project_pk>/', views.activity_planner_view, name='planner_activity_planner'),
    path('workforce/', views.workforce_view, name='planner_workforce'),
    path('configuration/', views.configuration_view, name='planner_configuration'),
    path('employee/<int:pk>/delete/', views.delete_employee_view, name='planner_delete_employee'),
    path('leave/<int:pk>/delete/', views.delete_leave_view, name='planner_delete_leave'), # New URL
    path('project/<int:pk>/delete/', views.delete_project_view, name='planner_delete_project'),
    path('activity/<int:pk>/edit/', views.edit_activity_view, name='planner_edit_activity'),
    path('activity/<int:pk>/delete/', views.delete_activity_view, name='planner_delete_activity'),
    path('holiday/<int:pk>/delete/', views.delete_holiday_view, name='planner_delete_holiday'),
    path('project-type/<int:pk>/edit/', views.edit_project_type_view, name='planner_edit_project_type'),
    path('project-type/<int:pk>/delete/', views.delete_project_type_view, name='planner_delete_project_type'),
    path('sales-forecast/', views.sales_forecast_view, name='planner_sales_forecast'),
    path('capacity-plan/', views.capacity_plan_view, name='planner_capacity_plan'),
    path('help/', views.help_view, name='planner_help_page'),
    path('effort-bracket/<int:pk>/delete/', views.delete_effort_bracket_view, name='planner_delete_effort_bracket'),
    path('api/project-type/<int:pk>/brackets/', views.get_effort_brackets_for_project_type, name='planner_get_effort_brackets'),
    path('api/project-type/<int:pk>/add-bracket/', views.add_effort_bracket_for_project_type, name='planner_add_effort_bracket'),
    path('employee/<int:pk>/toggle-status/', views.toggle_employee_status_view, name='planner_toggle_employee_status'),
    path('employee/<int:pk>/update/', views.update_employee_view, name='planner_update_employee'),
]