from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied

KB_PAGE_SIZE = 10

from accounts.models import Info

from .forms import (
    ArticleForm,
    ArticleCommentForm,
    QuestionForm,
    AnswerForm,
    ReportForm,
    ReportCommentForm,
)
from .models import (
    Article,
    ArticleAttachment,
    ArticleComment,
    ArticleRevision,
    Category,
    Question,
    Answer,
    Report,
    ReportComment,
    ReportAttachment,
    Vote,
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
    active_tab = request.GET.get('tab', 'wiki')
    if active_tab not in {'wiki', 'qa', 'reports'}:
        active_tab = 'wiki'
    query = request.GET.get('q', '').strip()

    context = {
        'active_tab': active_tab,
        'query': query,
    }
    context.update(get_kb_stats_context())

    if active_tab == 'wiki':
        articles = Article.objects.select_related('category', 'author', 'parent').prefetch_related('tags')
        if query:
            articles = articles.filter(
                models.Q(title__icontains=query) |
                models.Q(content__icontains=query) |
                models.Q(excerpt__icontains=query) |
                models.Q(category__name__icontains=query)
            )
        articles = articles.order_by('-updated_at')

        if query:
            # Flat, paginated results read better than a hierarchy built from a partial match set.
            hierarchy_articles = []
            other_articles_qs = articles
        else:
            hierarchy_articles = build_article_hierarchy(
                articles.filter(models.Q(is_hierarchy_root=True) | models.Q(parent__isnull=False))
            )
            other_articles_qs = articles.filter(parent__isnull=True, is_hierarchy_root=False)

        page_obj = Paginator(other_articles_qs, KB_PAGE_SIZE).get_page(request.GET.get('page'))
        context.update(get_kb_sidebar_context())
        context.update({
            'hierarchy_articles': hierarchy_articles,
            'other_articles': page_obj,
            'page_obj': page_obj,
        })
    elif active_tab == 'qa':
        qa_status = request.GET.get('qa_status', 'all')
        questions = Question.objects.select_related('author', 'accepted_answer').prefetch_related('tags').annotate(
            answer_count=Count('answers')
        )
        if query:
            questions = questions.filter(models.Q(title__icontains=query) | models.Q(body__icontains=query))
        if qa_status == 'solved':
            questions = questions.filter(is_solved=True)
        elif qa_status == 'unsolved':
            questions = questions.filter(is_solved=False)
        questions = questions.order_by('-created_at')

        page_obj = Paginator(questions, KB_PAGE_SIZE).get_page(request.GET.get('page'))
        context.update({
            'qa_status': qa_status,
            'questions': page_obj,
            'page_obj': page_obj,
        })
    else:
        report_type = request.GET.get('report_type', 'all')
        report_status = request.GET.get('report_status', 'all')
        report_priority = request.GET.get('report_priority', 'all')
        reports = Report.objects.select_related('application', 'reporter', 'assignee').prefetch_related('tags').annotate(
            comment_count=Count('comments')
        )
        if query:
            reports = reports.filter(
                models.Q(title__icontains=query) |
                models.Q(description__icontains=query) |
                models.Q(application__name__icontains=query)
            )
        if report_type != 'all':
            reports = reports.filter(type=report_type)
        if report_status != 'all':
            reports = reports.filter(status=report_status)
        if report_priority != 'all':
            reports = reports.filter(priority=report_priority)
        reports = reports.order_by('-updated_at')

        page_obj = Paginator(reports, KB_PAGE_SIZE).get_page(request.GET.get('page'))
        context.update({
            'report_type': report_type,
            'report_status': report_status,
            'report_priority': report_priority,
            'reports': page_obj,
            'page_obj': page_obj,
        })

    return render(request, 'home/forum_home.html', context)


@login_required
def article_category(request, slug):
    category = get_object_or_404(Category, slug=slug)
    query = request.GET.get('q', '').strip()
    articles = Article.objects.filter(category=category).select_related('author', 'parent').prefetch_related('tags')
    if query:
        articles = articles.filter(
            models.Q(title__icontains=query) |
            models.Q(content__icontains=query) |
            models.Q(excerpt__icontains=query)
        )
    articles = articles.order_by('-updated_at')

    if query:
        hierarchy_articles = []
        other_articles_qs = articles
    else:
        hierarchy_articles = build_article_hierarchy(
            articles.filter(models.Q(is_hierarchy_root=True) | models.Q(parent__isnull=False))
        )
        other_articles_qs = articles.filter(parent__isnull=True, is_hierarchy_root=False)

    page_obj = Paginator(other_articles_qs, KB_PAGE_SIZE).get_page(request.GET.get('page'))
    context = {
        'category': category,
        'query': query,
        'hierarchy_articles': hierarchy_articles,
        'other_articles': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'home/kb_category.html', context)


@login_required
def article_detail(request, slug):
    article = get_object_or_404(
        Article.objects.select_related('category', 'author').prefetch_related('tags', 'comments__author', 'attachments'),
        slug=slug
    )

    if request.method == 'POST':
        form = ArticleCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.article = article
            comment.author = request.user
            comment.save()
            messages.success(request, 'Comment added.')
            return redirect(article.get_absolute_url())
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ArticleCommentForm()

    Article.objects.filter(pk=article.pk).update(views=models.F('views') + 1)
    article.refresh_from_db(fields=['views'])
    context = {
        'article': article,
        'comments': article.comments.all(),
        'attachments': article.attachments.all(),
        'revisions': article.revisions.select_related('edited_by')[:20],
        'comment_form': form,
        'active_tab': 'wiki',
    }
    context.update(get_kb_stats_context())
    context.update(get_kb_sidebar_context())
    return render(request, 'home/kb_article_detail.html', context)


def _cast_vote(user, target, direction):
    """Toggle/switch a user's vote on a Question or Answer, keeping its `votes` counter in sync."""
    value = Vote.UP if direction == 'up' else Vote.DOWN
    lookup = {'user': user}
    if isinstance(target, Question):
        lookup['question'] = target
    else:
        lookup['answer'] = target

    existing = Vote.objects.filter(**lookup).first()
    if existing is None:
        Vote.objects.create(value=value, **lookup)
        delta = value
    elif existing.value == value:
        existing.delete()
        delta = -value
    else:
        delta = value - existing.value
        existing.value = value
        existing.save(update_fields=['value'])

    if delta:
        type(target).objects.filter(pk=target.pk).update(votes=models.F('votes') + delta)
        target.refresh_from_db(fields=['votes'])
    return target.votes


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

    user_votes = {
        vote.answer_id: vote.value
        for vote in Vote.objects.filter(user=request.user, answer__question=question)
    }
    question_vote = Vote.objects.filter(user=request.user, question=question).first()

    answers = list(question.answers.all())
    for answer in answers:
        answer.user_vote = user_votes.get(answer.id, 0)

    context = {
        'question': question,
        'answers': answers,
        'answer_form': form,
        'active_tab': 'qa',
        'user_question_vote': question_vote.value if question_vote else 0,
        'can_accept_answer': request.user.is_staff or question.author_id == request.user.id,
    }
    context.update(get_kb_stats_context())
    context.update(get_kb_sidebar_context())
    return render(request, 'home/kb_question_detail.html', context)


@login_required
@require_http_methods(['POST'])
def question_vote(request, pk, direction):
    if direction not in ('up', 'down'):
        raise Http404
    question = get_object_or_404(Question, pk=pk)
    if question.author_id == request.user.id:
        messages.error(request, "You can't vote on your own question.")
    else:
        _cast_vote(request.user, question, direction)
    return redirect('kb-question-detail', pk=question.pk)


@login_required
@require_http_methods(['POST'])
def answer_vote(request, pk, direction):
    if direction not in ('up', 'down'):
        raise Http404
    answer = get_object_or_404(Answer.objects.select_related('question'), pk=pk)
    if answer.author_id == request.user.id:
        messages.error(request, "You can't vote on your own answer.")
    else:
        _cast_vote(request.user, answer, direction)
    return redirect('kb-question-detail', pk=answer.question_id)


@login_required
@require_http_methods(['POST'])
def answer_accept(request, pk):
    answer = get_object_or_404(Answer.objects.select_related('question'), pk=pk)
    question = answer.question
    if not (request.user.is_staff or question.author_id == request.user.id):
        messages.error(request, 'Only the question author can accept an answer.')
        return redirect('kb-question-detail', pk=question.pk)

    if question.accepted_answer_id == answer.pk:
        Answer.objects.filter(pk=answer.pk).update(is_accepted=False)
        question.accepted_answer = None
        question.is_solved = False
        question.save(update_fields=['accepted_answer', 'is_solved'])
        messages.success(request, 'Answer unmarked as accepted.')
    else:
        Answer.objects.filter(question=question).update(is_accepted=False)
        Answer.objects.filter(pk=answer.pk).update(is_accepted=True)
        question.accepted_answer = answer
        question.is_solved = True
        question.save(update_fields=['accepted_answer', 'is_solved'])
        messages.success(request, 'Answer marked as accepted.')
    return redirect('kb-question-detail', pk=question.pk)


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
        form = ArticleForm(request.POST or None, request.FILES or None, user=request.user)
        if request.method == 'POST' and form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            form.save_m2m()
            attachments = form.cleaned_data.get('attachments', [])
            for uploaded_file in attachments:
                ArticleAttachment.objects.create(
                    article=article,
                    file=uploaded_file,
                    uploaded_by=request.user
                )
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

    # Captured before the form binds, since Django's ModelForm mutates the
    # instance in place during is_valid() -- reading article.* afterwards
    # would already reflect the *new* values, not what's being replaced.
    original = {'title': article.title, 'content': article.content, 'excerpt': article.excerpt}

    form = ArticleForm(request.POST or None, instance=article, user=request.user)
    if request.method == 'POST' and form.is_valid():
        if set(form.changed_data) & {'title', 'content', 'excerpt'}:
            ArticleRevision.objects.create(article=article, edited_by=request.user, **original)
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
@require_http_methods(['POST'])
def article_revision_restore(request, slug, revision_pk):
    article = get_object_or_404(Article, slug=slug)
    if not (request.user.is_staff or article.author == request.user):
        messages.error(request, 'You do not have permission to edit this article.')
        return redirect(article.get_absolute_url())

    revision = get_object_or_404(ArticleRevision, pk=revision_pk, article=article)

    ArticleRevision.objects.create(
        article=article,
        title=article.title,
        content=article.content,
        excerpt=article.excerpt,
        edited_by=request.user,
    )
    article.title = revision.title
    article.content = revision.content
    article.excerpt = revision.excerpt
    article.save(update_fields=['title', 'content', 'excerpt', 'updated_at'])
    messages.success(request, f'Restored the version from {revision.created_at:%Y-%m-%d %H:%M}.')
    return redirect(article.get_absolute_url())


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
