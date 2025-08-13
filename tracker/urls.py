from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='tracker_index'),
    path('login/', views.login_view, name='tracker_login'),
    path('signup/', views.signup_view, name='tracker_signup'),
    path('logout/', views.logout_view, name='tracker_logout'),
    path('project/new/', views.new_project, name='tracker_new_project'),
    path('project/<int:project_id>/', views.project_detail, name='tracker_project_detail'),
    #path('project/edit/<int:project_id>/', views.edit_project, name='tracker_edit_project'),
    path('project/<int:project_id>/delete/', views.delete_project, name='tracker_delete_project'),
    path('dashboard/', views.dashboard, name='tracker_dashboard'),
    path('project-reports/', views.project_reports, name='project_reports'),
    path('project/<int:project_id>/activity/', views.project_activity, name='tracker_project_activity'),
    path('upcoming-milestones/', views.upcoming_milestones, name='tracker_upcoming_milestones'),
    path('upcoming-milestones/export/excel/', views.export_milestones_excel, name='tracker_export_milestones_excel'),
    path('upcoming-milestones/export/pdf/', views.export_milestones_pdf, name='tracker_export_milestones_pdf'),
    path('remark/add/<int:stage_id>/', views.add_remark, name='tracker_add_remark'),
    path('remark/view/<int:stage_id>/', views.get_remarks, name='tracker_view_remarks'),
    path('project-reports/export/pdf/', views.export_report_pdf, name='export_report_pdf'),
    path('project/<int:project_id>/add_update/', views.add_project_update, name='add_project_update'),
    path('update/<int:update_id>/edit/', views.edit_project_update, name='edit_project_update'),
    path('update/<int:update_id>/delete/', views.delete_project_update, name='delete_project_update'),
    path('update/<int:update_id>/toggle_status/', views.toggle_update_status, name='toggle_update_status'),
    path('project/<int:project_id>/updates/', views.all_project_updates, name='all_project_updates'),
    path('update/<int:update_id>/mitigation/', views.save_mitigation_plan, name='save_mitigation_plan'),
    path('help/', views.help_page, name='help_page'),
]
