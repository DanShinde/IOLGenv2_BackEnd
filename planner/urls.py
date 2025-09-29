from django.urls import path
from . import views

urlpatterns = [
    path('', views.project_list_view, name='planner_project_list'),
    path('planner/all/', views.consolidated_planner_view, name='consolidated_planner'),
    path('planner/<int:project_pk>/', views.activity_planner_view, name='activity_planner'),
    path('workforce/', views.workforce_view, name='workforce'),
    path('configuration/', views.configuration_view, name='configuration'),
    path('employee/<int:pk>/delete/', views.delete_employee_view, name='delete_employee'),
    path('project/<int:pk>/delete/', views.delete_project_view, name='planner_delete_project'),
    path('activity/<int:pk>/edit/', views.edit_activity_view, name='edit_activity'),
    path('activity/<int:pk>/delete/', views.delete_activity_view, name='delete_activity'),
    path('holiday/<int:pk>/delete/', views.delete_holiday_view, name='delete_holiday'),
    path('project-type/<int:pk>/edit/', views.edit_project_type_view, name='edit_project_type'),
    path('project-type/<int:pk>/delete/', views.delete_project_type_view, name='delete_project_type'),
    path('sales-forecast/', views.sales_forecast_view, name='sales_forecast'),
    path('capacity-plan/', views.capacity_plan_view, name='capacity_plan'),
    path('help/', views.help_view, name='planner_help_page'),
    path('effort-bracket/<int:pk>/delete/', views.delete_effort_bracket_view, name='delete_effort_bracket'),

    # NEW: URLs for benchmark modal
    path('api/project-type/<int:pk>/brackets/', views.get_effort_brackets_for_project_type, name='get_effort_brackets'),
    path('api/project-type/<int:pk>/add-bracket/', views.add_effort_bracket_for_project_type, name='add_effort_bracket'),
]