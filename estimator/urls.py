from django.urls import path

from . import views

urlpatterns = [
    # Projects (main screens)
    path('', views.ProjectListView.as_view(), name='estimator_project_list'),
    path('projects/new/', views.ProjectCreateView.as_view(), name='estimator_project_new'),
    path('projects/<int:pk>/', views.ProjectDetailView.as_view(), name='estimator_project_builder'),
    path('projects/<int:pk>/edit/', views.ProjectUpdateView.as_view(), name='estimator_project_edit'),
    path('projects/<int:pk>/delete/', views.ProjectDeleteView.as_view(), name='estimator_project_delete'),
    path('projects/<int:pk>/duplicate/', views.project_duplicate, name='estimator_project_duplicate'),
    path('projects/<int:pk>/modules/sync/', views.project_modules_sync, name='estimator_project_modules_sync'),
    path('projects/<int:pk>/report/', views.ProjectReportView.as_view(), name='estimator_project_report'),
    path('projects/<int:pk>/report/pdf/', views.project_export_pdf, name='estimator_project_export_pdf'),
    path('projects/<int:pk>/report/excel/', views.project_export_excel, name='estimator_project_export_excel'),
    path('projects/<int:pk>/save-as-template/', views.ProjectSaveAsTemplateView.as_view(), name='estimator_project_save_as_template'),

    # Templates (reusable module-row presets, shared across all estimator users)
    path('templates/', views.ProjectTemplateListView.as_view(), name='estimator_template_list'),
    path('templates/new/', views.ProjectTemplateCreateView.as_view(), name='estimator_template_new'),
    path('templates/<int:pk>/', views.ProjectTemplateDetailView.as_view(), name='estimator_template_builder'),
    path('templates/<int:pk>/edit/', views.ProjectTemplateUpdateView.as_view(), name='estimator_template_edit'),
    path('templates/<int:pk>/delete/', views.ProjectTemplateDeleteView.as_view(), name='estimator_template_delete'),
    path('templates/<int:pk>/modules/sync/', views.template_modules_sync, name='estimator_template_modules_sync'),

    # Activity Master
    path('activities/', views.ActivityListView.as_view(), name='estimator_activity_list'),
    path('activities/new/', views.ActivityCreateView.as_view(), name='estimator_activity_new'),
    path('activities/<int:pk>/edit/', views.ActivityUpdateView.as_view(), name='estimator_activity_edit'),
    path('activities/<int:pk>/delete/', views.ActivityDeleteView.as_view(), name='estimator_activity_delete'),

    # Module Types + time matrix (Module Configuration, per Segment)
    path('module-types/', views.ModuleTypeListView.as_view(), name='estimator_module_type_list'),
    path('module-types/new/', views.ModuleTypeCreateView.as_view(), name='estimator_module_type_new'),
    path('module-types/<int:pk>/edit/', views.ModuleTypeUpdateView.as_view(), name='estimator_module_type_edit'),
    path('module-types/<int:pk>/delete/', views.ModuleTypeDeleteView.as_view(), name='estimator_module_type_delete'),
    path('module-types/<int:pk>/segments/', views.ModuleTypeSegmentsView.as_view(), name='estimator_module_type_segments'),
    path('module-types/<int:module_type_pk>/segments/<int:segment_pk>/matrix/', views.ModuleTypeMatrixView.as_view(), name='estimator_module_type_matrix'),

    # Segments
    path('segments/', views.SegmentListView.as_view(), name='estimator_segment_list'),
    path('segments/new/', views.SegmentCreateView.as_view(), name='estimator_segment_new'),
    path('segments/<int:pk>/edit/', views.SegmentUpdateView.as_view(), name='estimator_segment_edit'),
    path('segments/<int:pk>/delete/', views.SegmentDeleteView.as_view(), name='estimator_segment_delete'),

    # Complexity Levels
    path('complexity-levels/', views.ComplexityListView.as_view(), name='estimator_complexity_list'),
    path('complexity-levels/new/', views.ComplexityCreateView.as_view(), name='estimator_complexity_new'),
    path('complexity-levels/<int:pk>/edit/', views.ComplexityUpdateView.as_view(), name='estimator_complexity_edit'),
    path('complexity-levels/<int:pk>/delete/', views.ComplexityDeleteView.as_view(), name='estimator_complexity_delete'),
]
