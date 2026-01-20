from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import models
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied

from accounts.models import Info

from .forms import (
    ArticleForm,
    QuestionForm,
    AnswerForm,
    ReportForm,
    ReportCommentForm,
)
from .models import (
    Article,
    Category,
    Question,
    Answer,
    Report,
    ReportComment,
    ReportAttachment,
)


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


def build_article_hierarchy(articles):
    articles_list = list(articles)
    if not articles_list:
        return []

    articles_by_parent = {}
    articles_by_id = {}
    for article in articles_list:
        articles_by_id[article.id] = article
        articles_by_parent.setdefault(article.parent_id, []).append(article)

    roots = [article for article in articles_list if article.is_hierarchy_root]
    if not roots:
        roots = [article for article in articles_list if article.parent_id is None]

    for article in articles_list:
        if article.is_hierarchy_root:
            continue
        if article.parent_id and article.parent_id not in articles_by_id:
            roots.append(article)

    unique_roots = []
    seen_root_ids = set()
    for root in roots:
        if root.id in seen_root_ids:
            continue
        seen_root_ids.add(root.id)
        unique_roots.append(root)
    roots = sorted(unique_roots, key=lambda item: item.title.lower())

    hierarchy = []
    visited = set()

    def add_node(node, depth):
        if node.id in visited:
            return
        visited.add(node.id)
        hierarchy.append({'article': node, 'indent': depth * 18})
        children = articles_by_parent.get(node.id, [])
        for child in sorted(children, key=lambda item: item.title.lower()):
            add_node(child, depth + 1)

    for root in roots:
        add_node(root, 0)

    added_ids = {item['article'].id for item in hierarchy}
    leftovers = [article for article in articles_list if article.id not in added_ids]
    for article in sorted(leftovers, key=lambda item: item.title.lower()):
        hierarchy.append({'article': article, 'indent': 0})

    return hierarchy


def build_article_tree(articles):
    articles_list = list(articles)
    if not articles_list:
        return []

    articles_by_parent = {}
    articles_by_id = {}
    for article in articles_list:
        articles_by_id[article.id] = article
        articles_by_parent.setdefault(article.parent_id, []).append(article)

    roots = [article for article in articles_list if article.is_hierarchy_root]
    if not roots:
        roots = [article for article in articles_list if article.parent_id is None]

    for article in articles_list:
        if article.is_hierarchy_root:
            continue
        if article.parent_id and article.parent_id not in articles_by_id:
            roots.append(article)

    unique_roots = []
    seen_root_ids = set()
    for root in roots:
        if root.id in seen_root_ids:
            continue
        seen_root_ids.add(root.id)
        unique_roots.append(root)
    roots = sorted(unique_roots, key=lambda item: item.title.lower())

    visited = set()

    def build_node(node):
        if node.id in visited:
            return None
        visited.add(node.id)
        children = []
        for child in sorted(articles_by_parent.get(node.id, []), key=lambda item: item.title.lower()):
            child_node = build_node(child)
            if child_node:
                children.append(child_node)
        return {'article': node, 'children': children}

    tree = []
    for root in roots:
        node = build_node(root)
        if node:
            tree.append(node)

    leftovers = [article for article in articles_list if article.id not in visited]
    for article in sorted(leftovers, key=lambda item: item.title.lower()):
        tree.append({'article': article, 'children': []})

    return tree


def get_kb_stats_context():
    total_articles = Article.objects.count()
    total_questions = Question.objects.count()
    total_reports = Report.objects.count()
    total_interactions = Answer.objects.count() + ReportComment.objects.count()
    total_users = get_user_model().objects.count()
    open_bugs = Report.objects.filter(
        type=Report.TYPE_BUG,
        status__in=[Report.STATUS_OPEN, Report.STATUS_IN_PROGRESS]
    ).count()
    open_features = Report.objects.filter(
        type=Report.TYPE_FEATURE,
        status__in=[Report.STATUS_OPEN, Report.STATUS_IN_PROGRESS]
    ).count()
    return {
        'total_articles': total_articles,
        'total_questions': total_questions,
        'total_reports': total_reports,
        'total_interactions': total_interactions,
        'total_users': total_users,
        'open_bugs': open_bugs,
        'open_features': open_features,
    }


def get_kb_sidebar_context():
    hierarchy_tree = build_article_tree(
        Article.objects.only('id', 'title', 'slug', 'parent_id', 'is_hierarchy_root')
        .filter(models.Q(is_hierarchy_root=True) | models.Q(parent__isnull=False))
        .order_by('title')
    )
    other_articles_sidebar = Article.objects.only('id', 'title', 'slug').filter(
        parent__isnull=True,
        is_hierarchy_root=False
    ).order_by('title')
    return {
        'hierarchy_tree': hierarchy_tree,
        'other_articles_sidebar': other_articles_sidebar,
    }


@login_required
def forum_home(request):
    articles = Article.objects.select_related('category', 'author', 'parent').prefetch_related('tags').order_by('-updated_at')
    hierarchy_articles = build_article_hierarchy(
        articles.filter(models.Q(is_hierarchy_root=True) | models.Q(parent__isnull=False))
    )
    other_articles = articles.filter(parent__isnull=True, is_hierarchy_root=False)
    questions = Question.objects.select_related('author', 'accepted_answer').prefetch_related('tags').annotate(
        answer_count=Count('answers')
    ).order_by('-created_at')
    reports = Report.objects.select_related('application', 'reporter', 'assignee').prefetch_related('tags').annotate(
        comment_count=Count('comments')
    ).order_by('-updated_at')

    context = {
        'hierarchy_articles': hierarchy_articles,
        'other_articles': other_articles,
        'questions': questions,
        'reports': reports,
    }
    context.update(get_kb_stats_context())
    context.update(get_kb_sidebar_context())
    return render(request, 'home/forum_home.html', context)


@login_required
def article_category(request, slug):
    category = get_object_or_404(Category, slug=slug)
    articles = Article.objects.filter(category=category).select_related('author', 'parent').prefetch_related('tags').order_by('-updated_at')
    hierarchy_articles = build_article_hierarchy(
        articles.filter(models.Q(is_hierarchy_root=True) | models.Q(parent__isnull=False))
    )
    other_articles = articles.filter(parent__isnull=True, is_hierarchy_root=False)
    context = {
        'category': category,
        'hierarchy_articles': hierarchy_articles,
        'other_articles': other_articles,
    }
    return render(request, 'home/kb_category.html', context)


@login_required
def article_detail(request, slug):
    article = get_object_or_404(Article.objects.select_related('category', 'author').prefetch_related('tags'), slug=slug)
    Article.objects.filter(pk=article.pk).update(views=models.F('views') + 1)
    article.refresh_from_db(fields=['views'])
    context = {
        'article': article,
        'active_tab': 'wiki',
    }
    context.update(get_kb_stats_context())
    context.update(get_kb_sidebar_context())
    return render(request, 'home/kb_article_detail.html', context)


@login_required
def question_detail(request, pk):
    question = get_object_or_404(
        Question.objects.select_related('author', 'accepted_answer').prefetch_related('tags', 'answers__author'),
        pk=pk
    )

    if request.method == 'POST':
        form = AnswerForm(request.POST)
        if form.is_valid():
            answer = form.save(commit=False)
            answer.question = question
            answer.author = request.user
            answer.save()
            messages.success(request, 'Answer posted.')
            return redirect('kb-question-detail', pk=question.pk)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = AnswerForm()

    context = {
        'question': question,
        'answers': question.answers.all(),
        'answer_form': form,
        'active_tab': 'qa',
    }
    context.update(get_kb_stats_context())
    context.update(get_kb_sidebar_context())
    return render(request, 'home/kb_question_detail.html', context)


@login_required
def report_detail(request, pk):
    report = get_object_or_404(
        Report.objects.select_related('application', 'reporter', 'assignee').prefetch_related('tags', 'comments__author', 'attachments'),
        pk=pk
    )

    if request.method == 'POST':
        form = ReportCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.report = report
            comment.author = request.user
            comment.save()
            messages.success(request, 'Comment added.')
            return redirect('kb-report-detail', pk=report.pk)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ReportCommentForm()

    context = {
        'report': report,
        'comments': report.comments.all(),
        'attachments': report.attachments.all(),
        'comment_form': form,
        'active_tab': 'reports',
    }
    context.update(get_kb_stats_context())
    context.update(get_kb_sidebar_context())
    return render(request, 'home/kb_report_detail.html', context)


@login_required
def kb_create(request):
    content_type = request.GET.get('type', '')
    form = None
    template = 'home/kb_create.html'

    if request.method == 'POST':
        content_type = request.POST.get('content_type', content_type)

    if content_type not in {'wiki', 'qa', 'report'}:
        content_type = ''

    if content_type == 'wiki':
        form = ArticleForm(request.POST or None, user=request.user)
        if request.method == 'POST' and form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            form.save_m2m()
            messages.success(request, 'Article created.')
            return redirect(article.get_absolute_url())
        if request.method == 'POST' and form.errors:
            messages.error(request, 'Please correct the errors below.')
    elif content_type == 'qa':
        form = QuestionForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            question = form.save(commit=False)
            question.author = request.user
            question.save()
            form.save_m2m()
            messages.success(request, 'Question posted.')
            return redirect(question.get_absolute_url())
        if request.method == 'POST' and form.errors:
            messages.error(request, 'Please correct the errors below.')
    elif content_type == 'report':
        form = ReportForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.save()
            form.save_m2m()
            attachments = form.cleaned_data.get('attachments', [])
            for uploaded_file in attachments:
                ReportAttachment.objects.create(
                    report=report,
                    file=uploaded_file,
                    uploaded_by=request.user
                )
            messages.success(request, 'Report submitted.')
            return redirect(report.get_absolute_url())
        if request.method == 'POST' and form.errors:
            messages.error(request, 'Please correct the errors below.')

    context = {
        'content_type': content_type,
        'form': form,
    }
    return render(request, template, context)


@login_required
def article_update(request, slug):
    article = get_object_or_404(Article, slug=slug)
    if not (request.user.is_staff or article.author == request.user):
        messages.error(request, 'You do not have permission to edit this article.')
        return redirect(article.get_absolute_url())

    form = ArticleForm(request.POST or None, instance=article, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Article updated.')
        return redirect(article.get_absolute_url())

    context = {
        'content_type': 'wiki',
        'form': form,
        'object': article,
    }
    return render(request, 'home/kb_create.html', context)


@login_required
def question_update(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if not (request.user.is_staff or question.author == request.user):
        messages.error(request, 'You do not have permission to edit this question.')
        return redirect(question.get_absolute_url())

    form = QuestionForm(request.POST or None, instance=question)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Question updated.')
        return redirect(question.get_absolute_url())

    context = {
        'content_type': 'qa',
        'form': form,
        'object': question,
    }
    return render(request, 'home/kb_create.html', context)


@login_required
def report_update(request, pk):
    report = get_object_or_404(Report, pk=pk)
    if not (request.user.is_staff or report.reporter == request.user):
        messages.error(request, 'You do not have permission to edit this report.')
        return redirect(report.get_absolute_url())

    form = ReportForm(request.POST or None, instance=report)
    if request.method == 'POST' and form.is_valid():
        updated_report = form.save(commit=False)
        if updated_report.status in [Report.STATUS_RESOLVED, Report.STATUS_CLOSED] and not updated_report.resolved_at:
            updated_report.resolved_at = timezone.now()
        if updated_report.status in [Report.STATUS_OPEN, Report.STATUS_IN_PROGRESS]:
            updated_report.resolved_at = None
        updated_report.save()
        form.save_m2m()
        messages.success(request, 'Report updated.')
        return redirect(report.get_absolute_url())

    context = {
        'content_type': 'report',
        'form': form,
        'object': report,
    }
    return render(request, 'home/kb_create.html', context)
