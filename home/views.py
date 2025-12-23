from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from accounts.models import Info
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Prefetch
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from django.db import transaction
from datetime import datetime
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied

from .models import (
    ForumCategory, ForumThread, ForumPost,
    ForumAttachment, ForumTag
)
from .forms import (
    ThreadCreateForm, ThreadUpdateForm, PostCreateForm,
    ThreadFilterForm
)


# ============================================================================
# EXISTING VIEWS
# ============================================================================

@login_required
def home(request):
    return render(request, 'base.html')


@login_required
def downloads(request):
    infos = Info.objects.all()
    context = {
        'infos': infos
    }
    return render(request, 'home/downloads.html', context)


def superuser_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@superuser_required
def clear_cache(request):
    cache.clear()
    return JsonResponse({"status": "ok", "message": "Cache cleared"})


# ============================================================================
# FORUM UTILITY FUNCTIONS
# ============================================================================

def get_cache_key(prefix, **filters):
    """Generate cache key with versioning"""
    filter_parts = []
    for key, value in sorted(filters.items()):
        if value is not None and value != '':
            filter_parts.append(f"{key}:{value}")

    filter_string = "_".join(filter_parts) if filter_parts else "all"
    version = cache.get(f"{prefix}_version", 0)
    return f"{prefix}:v{version}:{filter_string}"


def invalidate_cache(prefix):
    """Invalidate cache by incrementing version"""
    cache_version_key = f"{prefix}_version"
    current_version = cache.get(cache_version_key, 0)
    cache.set(cache_version_key, current_version + 1, None)


class ForumPaginator:
    """Custom paginator for forum views"""
    page_size = 20
    max_page_size = 100

    @staticmethod
    def paginate_queryset(queryset, request, page_size=None):
        page_size = page_size or request.GET.get('page_size', ForumPaginator.page_size)
        try:
            page_size = min(int(page_size), ForumPaginator.page_size)
        except (TypeError, ValueError):
            page_size = ForumPaginator.page_size

        page = request.GET.get('page', 1)
        paginator = Paginator(queryset, page_size)

        try:
            paginated_data = paginator.page(page)
        except PageNotAnInteger:
            paginated_data = paginator.page(1)
        except EmptyPage:
            paginated_data = paginator.page(paginator.num_pages)

        return paginated_data, paginator


# ============================================================================
# FORUM MAIN VIEWS
# ============================================================================

@login_required
def forum_home(request):
    """Forum homepage showing all categories and recent threads"""
    categories = ForumCategory.objects.filter(is_active=True).prefetch_related(
        Prefetch('threads',
                queryset=ForumThread.objects.select_related('author').order_by('-last_activity_at'),
                to_attr='recent_threads_list')
    )

    recent_threads = ForumThread.objects.select_related(
        'category', 'author', 'best_answer'
    ).annotate(
        reply_count=Count('posts')
    ).order_by('-last_activity_at')[:10]

    total_threads = ForumThread.objects.count()
    total_posts = ForumPost.objects.count()
    total_users = ForumThread.objects.values('author').distinct().count()

    context = {
        'categories': categories,
        'recent_threads': recent_threads,
        'total_threads': total_threads,
        'total_posts': total_posts,
        'total_users': total_users,
    }
    return render(request, 'home/forum_home.html', context)


@login_required
def forum_category(request, slug):
    """View threads in a specific category"""
    category = get_object_or_404(ForumCategory, slug=slug, is_active=True)

    filter_form = ThreadFilterForm(request.GET)
    filter_params = {
        'status': request.GET.get('status', ''),
        'priority': request.GET.get('priority', ''),
        'search': request.GET.get('search', ''),
        'sort_by': request.GET.get('sort', '-last_activity_at'),
    }

    threads = ForumThread.objects.filter(category=category).select_related(
        'author', 'best_answer'
    ).prefetch_related('tags').annotate(
        reply_count=Count('posts')
    )

    if filter_params['status']:
        threads = threads.filter(status=filter_params['status'])

    if filter_params['priority']:
        threads = threads.filter(priority=filter_params['priority'])

    if filter_params['search']:
        threads = threads.filter(
            Q(title__icontains=filter_params['search']) |
            Q(content__icontains=filter_params['search'])
        )

    # Handle sorting
    sort = filter_params['sort_by']
    if sort == '-last_activity_at' or sort == 'recent':
        threads = threads.order_by('-is_pinned', '-last_activity_at')
    elif sort == '-created_at':
        threads = threads.order_by('-is_pinned', '-created_at')
    elif sort == 'created_at':
        threads = threads.order_by('-is_pinned', 'created_at')
    elif sort == '-views':
        threads = threads.order_by('-is_pinned', '-views')
    elif sort == '-is_pinned,-last_activity_at':
        threads = threads.order_by('-is_pinned', '-last_activity_at')
    else:
        threads = threads.order_by('-is_pinned', '-last_activity_at')

    paginated_threads, paginator = ForumPaginator.paginate_queryset(threads, request)

    context = {
        'category': category,
        'threads': paginated_threads,
        'threads_count': threads.count(),
        'paginator': paginator,
        'filter_form': filter_form,
        'status_filter': filter_params['status'],
        'sort': sort,
        'is_paginated': paginator.num_pages > 1,
    }
    return render(request, 'home/forum_category.html', context)


@login_required
def thread_detail(request, slug):
    """View thread details and posts"""
    thread = get_object_or_404(
        ForumThread.objects.select_related('category', 'author', 'best_answer'),
        slug=slug
    )

    thread.views += 1
    thread.save(update_fields=['views'])

    posts = thread.posts.select_related('author').prefetch_related(
        'upvotes', 'attachments', 'replies__author'
    )

    if request.method == 'POST':
        post_form = PostCreateForm(request.POST, request.FILES)
        if post_form.is_valid():
            post = post_form.save(commit=False)
            post.thread = thread
            post.author = request.user
            post.save()

            attachments = post_form.cleaned_data.get('attachments', [])
            for uploaded_file in attachments:
                ForumAttachment.objects.create(
                    thread=thread,
                    post=post,
                    file=uploaded_file,
                    uploaded_by=request.user
                )

            thread.last_activity_at = datetime.now()
            thread.save(update_fields=['last_activity_at'])

            messages.success(request, 'Your reply has been posted!')
            return redirect('forum-thread-detail', slug=thread.slug)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        post_form = PostCreateForm()

    paginated_posts, paginator = ForumPaginator.paginate_queryset(posts, request, page_size=10)
    can_edit = request.user.is_staff or thread.author == request.user

    context = {
        'thread': thread,
        'posts': paginated_posts,
        'paginator': paginator,
        'post_form': post_form,
        'can_edit': can_edit,
        'is_paginated': paginator.num_pages > 1,
    }
    return render(request, 'home/thread_detail.html', context)


@login_required
def thread_create(request):
    """Create a new thread"""
    if request.method == 'POST':
        form = ThreadCreateForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                thread = form.save(commit=False)
                thread.author = request.user
                thread.save()

                tags = form.cleaned_data.get('tags', [])
                thread.tags.set(tags)

                attachments = form.cleaned_data.get('attachments', [])
                for uploaded_file in attachments:
                    ForumAttachment.objects.create(
                        thread=thread,
                        file=uploaded_file,
                        uploaded_by=request.user
                    )

                invalidate_cache('forum_threads')
                messages.success(request, 'Thread created successfully!')
                return redirect('forum-thread-detail', slug=thread.slug)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ThreadCreateForm()

    # Get all categories for visual selection
    categories = ForumCategory.objects.filter(is_active=True).order_by('order', 'name')

    context = {
        'form': form,
        'title': 'Create New Thread',
        'categories': categories,
    }
    return render(request, 'home/thread_form.html', context)


@login_required
def thread_update(request, slug):
    """Update thread details"""
    thread = get_object_or_404(ForumThread, slug=slug)

    if not (request.user.is_staff or thread.author == request.user):
        messages.error(request, 'You do not have permission to edit this thread.')
        return redirect('forum-thread-detail', slug=thread.slug)

    if request.method == 'POST':
        form = ThreadUpdateForm(request.POST, instance=thread)
        if form.is_valid():
            form.save()
            invalidate_cache('forum_threads')
            messages.success(request, 'Thread updated successfully!')
            return redirect('forum-thread-detail', slug=thread.slug)
    else:
        form = ThreadUpdateForm(instance=thread)

    # Get all categories for visual selection
    categories = ForumCategory.objects.filter(is_active=True).order_by('order', 'name')

    context = {
        'form': form,
        'thread': thread,
        'title': 'Edit Thread',
        'categories': categories,
    }
    return render(request, 'home/thread_form.html', context)


@login_required
@require_http_methods(["POST"])
def post_create(request, slug):
    """Create a new post/reply in a thread"""
    thread = get_object_or_404(ForumThread, slug=slug)

    if thread.is_locked and not request.user.is_staff:
        messages.error(request, 'This thread is locked.')
        return redirect('forum-thread-detail', slug=thread.slug)

    content = request.POST.get('content', '').strip()
    parent_id = request.POST.get('parent_id')

    if not content:
        messages.error(request, 'Reply content cannot be empty.')
        return redirect('forum-thread-detail', slug=thread.slug)

    with transaction.atomic():
        post = ForumPost.objects.create(
            thread=thread,
            author=request.user,
            content=content
        )

        if parent_id:
            try:
                parent_post = ForumPost.objects.get(id=parent_id, thread=thread)
                post.parent = parent_post
                post.save(update_fields=['parent'])
            except ForumPost.DoesNotExist:
                pass

        thread.last_activity_at = datetime.now()
        thread.save(update_fields=['last_activity_at'])

    messages.success(request, 'Your reply has been posted!')
    return redirect('forum-thread-detail', slug=thread.slug)


# ============================================================================
# AJAX ENDPOINTS
# ============================================================================

@login_required
@require_http_methods(["POST"])
def post_upvote(request, post_id):
    """Toggle upvote on a post"""
    post = get_object_or_404(ForumPost, id=post_id)

    if request.user in post.upvotes.all():
        post.upvotes.remove(request.user)
        upvoted = False
    else:
        post.upvotes.add(request.user)
        upvoted = True

    return JsonResponse({
        'success': True,
        'upvoted': upvoted,
        'upvote_count': post.upvotes.count()
    })


@login_required
@require_http_methods(["POST"])
def mark_solution(request, post_id):
    """Mark a post as the solution"""
    post = get_object_or_404(ForumPost, id=post_id)
    thread = post.thread

    if not (request.user.is_staff or thread.author == request.user):
        return JsonResponse({
            'success': False,
            'message': 'You do not have permission to mark solutions.'
        }, status=403)

    post.mark_as_solution()
    invalidate_cache('forum_threads')

    return JsonResponse({
        'success': True,
        'message': 'Post marked as solution!'
    })


@login_required
@require_http_methods(["POST"])
def thread_lock_toggle(request, slug):
    """Lock/unlock a thread"""
    thread = get_object_or_404(ForumThread, slug=slug)

    if not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'message': 'Only staff can lock threads.'
        }, status=403)

    thread.is_locked = not thread.is_locked
    thread.save(update_fields=['is_locked'])

    return JsonResponse({
        'success': True,
        'is_locked': thread.is_locked
    })


@login_required
@require_http_methods(["POST"])
def thread_pin_toggle(request, slug):
    """Pin/unpin a thread"""
    thread = get_object_or_404(ForumThread, slug=slug)

    if not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'message': 'Only staff can pin threads.'
        }, status=403)

    thread.is_pinned = not thread.is_pinned
    thread.save(update_fields=['is_pinned'])
    invalidate_cache('forum_threads')

    return JsonResponse({
        'success': True,
        'is_pinned': thread.is_pinned
    })