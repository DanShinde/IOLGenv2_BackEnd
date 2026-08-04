from django.urls import path

from . import views

urlpatterns = [
    # SPA shell
    path('', views.index, name='testvault_index'),
    path('report/', views.report, name='testvault_report'),

    # Reference data / generation / excel (ported from the source Flask app)
    path('api/changelog/', views.api_changelog, name='testvault_api_changelog'),
    path('api/manual/', views.api_manual, name='testvault_api_manual'),
    path('api/test-groups/', views.api_test_groups, name='testvault_api_test_groups'),
    path('api/generate-test-cases/', views.api_generate_test_cases, name='testvault_api_generate_test_cases'),
    path('api/generate-workbook/', views.api_generate_workbook, name='testvault_api_generate_workbook'),
    path('api/custom-test-cases/', views.api_custom_test_cases, name='testvault_api_custom_test_cases'),
    path('api/custom-test-cases/add/', views.api_custom_test_cases_add, name='testvault_api_custom_test_cases_add'),
    path('api/custom-test-cases/delete/', views.api_custom_test_cases_delete, name='testvault_api_custom_test_cases_delete'),
    path('api/edit-test-groups/', views.api_edit_test_groups, name='testvault_api_edit_test_groups'),

    # Shareable report sessions
    path('api/report/create/', views.api_report_create, name='testvault_api_report_create'),
    path('api/report/update/<str:report_id>/', views.api_report_update, name='testvault_api_report_update'),
    path('api/report/data/<str:report_id>/', views.api_report_data, name='testvault_api_report_data'),

    # Template import/export
    path('api/template/download/', views.api_template_download, name='testvault_api_template_download'),
    path('api/template/upload/', views.api_template_upload, name='testvault_api_template_upload'),

    # Project CRUD (DB-backed, tied to tracker.Project / employees.Employee)
    path('api/projects/', views.api_project_list, name='testvault_api_project_list'),
    path('api/projects/create/', views.api_project_create, name='testvault_api_project_create'),
    path('api/projects/<int:pk>/', views.api_project_detail, name='testvault_api_project_detail'),
    path('api/projects/<int:pk>/save/', views.api_project_save, name='testvault_api_project_save'),
    path('api/projects/<int:pk>/duplicate/', views.api_project_duplicate, name='testvault_api_project_duplicate'),
    path('api/projects/<int:pk>/delete/', views.api_project_delete, name='testvault_api_project_delete'),

    # Lookups
    path('api/lookup/tracker-projects/', views.api_lookup_tracker_projects, name='testvault_api_lookup_tracker_projects'),
    path('api/lookup/planner-projects/', views.api_lookup_planner_projects, name='testvault_api_lookup_planner_projects'),
    path('api/lookup/employees/', views.api_lookup_employees, name='testvault_api_lookup_employees'),
]
