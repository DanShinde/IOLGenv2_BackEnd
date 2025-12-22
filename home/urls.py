from django.urls import path, include
from . import views


urlpatterns = [
    # Existing Home URLs
    path('', views.home, name='home'),
    path('downloads/', views.downloads, name='downloads'),
    path('cacheclear/', views.clear_cache, name='cache-clear'),

    # Forum URLs - all under /forum/ prefix
    path('forum/', views.forum_home, name='forum-home'),
    path('forum/category/<slug:slug>/', views.forum_category, name='forum-category'),
    path('forum/thread/create/', views.thread_create, name='forum-thread-create'),
    path('forum/thread/<slug:slug>/', views.thread_detail, name='forum-thread-detail'),
    path('forum/thread/<slug:slug>/edit/', views.thread_update, name='forum-thread-update'),

    # Forum AJAX Endpoints - all under /forum/
    path('forum/post/<int:post_id>/upvote/', views.post_upvote, name='forum-post-upvote'),
    path('forum/post/<int:post_id>/mark-solution/', views.mark_solution, name='forum-mark-solution'),
    path('forum/thread/<slug:slug>/lock/', views.thread_lock_toggle, name='forum-thread-lock'),
    path('forum/thread/<slug:slug>/pin/', views.thread_pin_toggle, name='forum-thread-pin'),
]
