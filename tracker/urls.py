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
    path('dashboard/stage-filter/', views.stage_filter_dashboard, name='tracker_stage_filter_dashboard'),
    path('project/<int:project_id>/activity/', views.project_activity, name='tracker_project_activity'),
    path('upcoming-milestones/', views.upcoming_milestones, name='tracker_upcoming_milestones'),
    path('upcoming-milestones/export/excel/', views.export_milestones_excel, name='tracker_export_milestones_excel'),
    path('upcoming-milestones/export/pdf/', views.export_milestones_pdf, name='tracker_export_milestones_pdf'),
    path('remark/add/<int:stage_id>/', views.add_remark, name='tracker_add_remark'),
    path('remark/view/<int:stage_id>/', views.get_remarks, name='tracker_view_remarks'),
]
