from django.urls import path, include
from . import views


urlpatterns = [
    # Existing Home URLs
    path('', views.home, name='home'),
    path('downloads/', views.downloads, name='downloads'),
    path('cacheclear/', views.clear_cache, name='cache-clear'),

    # Knowledge Base / Forum URLs
    path('forum/', views.forum_home, name='forum-home'),
    path('forum/category/<slug:slug>/', views.article_category, name='kb-category'),
    path('forum/create/', views.kb_create, name='kb-create'),
    path('forum/wiki/<slug:slug>/', views.article_detail, name='kb-article-detail'),
    path('forum/wiki/<slug:slug>/edit/', views.article_update, name='kb-article-edit'),
    path('forum/questions/<int:pk>/', views.question_detail, name='kb-question-detail'),
    path('forum/questions/<int:pk>/edit/', views.question_update, name='kb-question-edit'),
    path('forum/reports/<int:pk>/', views.report_detail, name='kb-report-detail'),
    path('forum/reports/<int:pk>/edit/', views.report_update, name='kb-report-edit'),
]
