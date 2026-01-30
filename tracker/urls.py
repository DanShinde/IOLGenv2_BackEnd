from django.urls import path, register_converter
from . import views
from uuid import UUID

class UUIDConverter:
    regex = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

    def to_python(self, value):
        return UUID(value)

    def to_url(self, value):
        return str(value)

register_converter(UUIDConverter, 'uuid')

urlpatterns = [
    path('index', views.index, name='tracker_index'),
    path('login/', views.login_view, name='tracker_login'),
    path('logout/', views.logout_view, name='tracker_logout'),
    path('signup/', views.signup_view, name='tracker_signup'),
    
    path('project/new/', views.new_project, name='tracker_new_project'),
    path('project/<int:project_id>/', views.project_detail, name='tracker_project_detail'),
    path('project/<int:project_id>/edit/', views.edit_project, name='tracker_edit_project'),
    path('project/<int:project_id>/delete/', views.delete_project, name='tracker_delete_project'),
    path('dashboard/', views.dashboard, name='tracker_dashboard'),
    path('project/reports/', views.project_reports, name='project_reports'),
    path('project/<int:project_id>/activity/', views.project_activity, name='tracker_project_activity'),

    # ✅ FIXED: Restored original names 'tracker_...' to match base.html
    path('upcoming-milestones/', views.upcoming_milestones, name='tracker_upcoming_milestones'),
    path('upcoming-milestones/export/excel/', views.export_milestones_excel, name='tracker_export_milestones_excel'),
    path('upcoming-milestones/export/pdf/', views.export_milestones_pdf, name='tracker_export_milestones_pdf'),
    
    path('reports/export/pdf/', views.export_report_pdf, name='export_report_pdf'),

    # Remark editing - Restored names to prevent breaking other templates
    path('remark/<int:remark_id>/edit/', views.edit_remark, name='tracker_edit_remark'),
    path('remark/<int:remark_id>/delete/', views.delete_remark, name='tracker_delete_remark'),
    path('remark/add/<int:stage_id>/', views.add_remark, name='tracker_add_remark'),
    path('remark/view/<int:stage_id>/', views.get_remarks, name='tracker_view_remarks'),
    
    # Project Comments (Notes)
    path('comment/<int:comment_id>/edit/', views.edit_project_comment, name='edit_project_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_project_comment, name='delete_project_comment'),

    # Project Updates
    path('project/<int:project_id>/add_update/', views.add_project_update, name='add_project_update'),
    path('update/<int:update_id>/edit/', views.edit_project_update, name='edit_project_update'),
    path('update/<int:update_id>/delete/', views.delete_project_update, name='delete_project_update'),
    path('update/<int:update_id>/toggle/', views.toggle_update_status, name='toggle_update_status'),
    path('update/<int:update_id>/mitigation/', views.save_mitigation_plan, name='save_mitigation_plan'),
    path('project/<int:project_id>/updates/', views.all_project_updates, name='all_project_updates'),
    
    # ✅ FIXED: Correct URL for All Push-Pull Content
    path('all-push-pull-content/', views.all_push_pull_content, name='all_push_pull_content'),
    path('all-push-pull-content/<str:filter>/', views.all_push_pull_content, name='all_push_pull_content_filtered'),

    path('push-pull/add/general/', views.add_general_update, name='add_general_update'),

    # Export URLs
    path('push-pull/export/excel/', views.export_push_pull_excel, name='export_push_pull_excel'),
    path('push-pull/export/pdf/', views.export_push_pull_pdf, name='export_push_pull_pdf'),

    # AJAX for Contact Person
    path('contact/add/ajax/', views.add_contact_person_ajax, name='add_contact_person_ajax'),
    
    # ✅ FIXED: Restored 'help_page' name to match base.html
    path('help/', views.help_page, name='help_page'), 

    # Ajax
    path('ajax/update-stage/<int:stage_id>/', views.update_stage_ajax, name='update_stage_ajax'),
    # This is the new one for our inline table editing
    path('ajax/update-project-update/', views.update_project_update_ajax, name='update_project_update_ajax'),

    # Remark on Update
    path('update/<int:update_id>/remark/add/', views.add_update_remark, name='add_update_remark'),
    path('update-remark/<int:remark_id>/edit/', views.edit_update_remark, name='edit_update_remark'),
    path('update-remark/<int:remark_id>/delete/', views.delete_update_remark, name='delete_update_remark'),

    # Public View
    path('public/push-pull/<uuid:access_token>/', views.public_push_pull_content, name='public_push_pull_content'),
]