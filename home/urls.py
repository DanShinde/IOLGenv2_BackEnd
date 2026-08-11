from django.urls import path, include
from . import views


urlpatterns = [
    # Existing Home URLs
    path('', views.home, name='home'),
    path('downloads/', views.downloads, name='downloads'),
    path('cacheclear/', views.clear_cache, name='cache-clear'),

    # Knowledge Base / Forum URLs
    path('forum/', views.forum_home, name='forum-home'),
    path('forum/notifications/', views.notifications_list, name='kb-notifications'),
    path('forum/category/<slug:slug>/', views.article_category, name='kb-category'),
    path('forum/tag/<slug:slug>/', views.tag_detail, name='kb-tag-detail'),
    path('forum/people/<str:username>/', views.user_profile, name='kb-user-profile'),
    path('forum/create/', views.kb_create, name='kb-create'),
    path('forum/wiki/<slug:slug>/', views.article_detail, name='kb-article-detail'),
    path('forum/wiki/<slug:slug>/edit/', views.article_update, name='kb-article-edit'),
    path('forum/wiki/<slug:slug>/delete/', views.article_delete, name='kb-article-delete'),
    path('forum/wiki/<slug:slug>/revisions/<int:revision_pk>/restore/', views.article_revision_restore, name='kb-article-revision-restore'),
    path('forum/wiki/comments/<int:pk>/edit/', views.article_comment_update, name='kb-article-comment-edit'),
    path('forum/wiki/comments/<int:pk>/delete/', views.article_comment_delete, name='kb-article-comment-delete'),
    path('forum/questions/<int:pk>/', views.question_detail, name='kb-question-detail'),
    path('forum/questions/<int:pk>/edit/', views.question_update, name='kb-question-edit'),
    path('forum/questions/<int:pk>/delete/', views.question_delete, name='kb-question-delete'),
    path('forum/questions/<int:pk>/vote/<str:direction>/', views.question_vote, name='kb-question-vote'),
    path('forum/answers/<int:pk>/vote/<str:direction>/', views.answer_vote, name='kb-answer-vote'),
    path('forum/answers/<int:pk>/accept/', views.answer_accept, name='kb-answer-accept'),
    path('forum/answers/<int:pk>/edit/', views.answer_update, name='kb-answer-edit'),
    path('forum/answers/<int:pk>/delete/', views.answer_delete, name='kb-answer-delete'),
    path('forum/reports/<int:pk>/', views.report_detail, name='kb-report-detail'),
    path('forum/reports/<int:pk>/edit/', views.report_update, name='kb-report-edit'),
    path('forum/reports/<int:pk>/delete/', views.report_delete, name='kb-report-delete'),
    path('forum/reports/comments/<int:pk>/edit/', views.report_comment_update, name='kb-report-comment-edit'),
    path('forum/reports/comments/<int:pk>/delete/', views.report_comment_delete, name='kb-report-comment-delete'),
]
