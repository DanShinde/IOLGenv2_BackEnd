from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils.timezone import now
from django.urls import reverse
import uuid
from pathlib import Path


# ============================================================================
# FORUM SYSTEM MODELS - Enhanced Bug Reports with Threading
# ============================================================================

class ForumCategory(models.Model):
    """Categories for organizing forum threads (e.g., Bug Reports, Feature Requests, Q&A)"""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='fa-comments', help_text='FontAwesome icon class')
    color = models.CharField(max_length=7, default='#667eea', help_text='Hex color code')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'Forum Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('forum-category', kwargs={'slug': self.slug})

    @property
    def thread_count(self):
        return self.threads.count()

    @property
    def post_count(self):
        return ForumPost.objects.filter(thread__category=self).count()


class ForumThread(models.Model):
    """Main discussion thread (enhanced bug report)"""
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_CLOSED, 'Closed'),
    ]

    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_CRITICAL = 'critical'

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_CRITICAL, 'Critical'),
    ]

    category = models.ForeignKey(ForumCategory, on_delete=models.CASCADE, related_name='threads')
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    content = models.TextField(help_text='Main content/description')

    # Bug report specific fields
    application_version = models.CharField(max_length=100, blank=True)
    steps_to_reproduce = models.TextField(blank=True)
    log_text = models.TextField(blank=True)

    # Thread metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)

    # User interactions
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='forum_threads')
    is_pinned = models.BooleanField(default=False, db_index=True)
    is_locked = models.BooleanField(default=False)
    views = models.PositiveIntegerField(default=0)

    # Best answer
    best_answer = models.ForeignKey('ForumPost', on_delete=models.SET_NULL, null=True, blank=True, related_name='best_answer_for')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-is_pinned', '-last_activity_at']
        indexes = [
            models.Index(fields=['-is_pinned', '-last_activity_at']),
            models.Index(fields=['category', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while ForumThread.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('forum-thread-detail', kwargs={'slug': self.slug})

    @property
    def post_count(self):
        return self.posts.count()

    @property
    def is_resolved(self):
        return self.status in [self.STATUS_RESOLVED, self.STATUS_CLOSED]


class ForumPost(models.Model):
    """Replies/comments on a thread"""
    thread = models.ForeignKey(ForumThread, on_delete=models.CASCADE, related_name='posts')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='forum_posts')
    content = models.TextField()

    # Threading support
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')

    # User interactions
    upvotes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='upvoted_posts', blank=True)
    is_solution = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Post by {self.author.username} on {self.thread.title}"

    @property
    def upvote_count(self):
        return self.upvotes.count()

    def mark_as_solution(self):
        """Mark this post as the best answer"""
        self.is_solution = True
        self.save()
        self.thread.best_answer = self
        self.thread.status = ForumThread.STATUS_RESOLVED
        self.thread.save()


def forum_attachment_upload_to(instance, filename):
    """Generate unique upload path for forum attachments"""
    ext = filename.split('.')[-1]
    timestamp = now().strftime('%Y%m%d_%H%M%S')
    unique_name = f"{uuid.uuid4().hex}_{timestamp}.{ext}"
    return f"forum/{instance.thread.id}/{unique_name}"


class ForumAttachment(models.Model):
    """File attachments for threads and posts"""
    thread = models.ForeignKey(ForumThread, on_delete=models.CASCADE, related_name='attachments')
    post = models.ForeignKey(ForumPost, on_delete=models.CASCADE, null=True, blank=True, related_name='attachments')

    file = models.FileField(upload_to=forum_attachment_upload_to)
    file_type = models.CharField(max_length=10, blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='forum_uploads')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.original_name or Path(self.file.name).name

    def save(self, *args, **kwargs):
        if self.file:
            self.original_name = self.file.name
            self.file_size = self.file.size
            if hasattr(self.file, 'content_type'):
                if self.file.content_type.startswith('image/'):
                    self.file_type = 'image'
                elif self.file.content_type.startswith('video/'):
                    self.file_type = 'video'
                else:
                    self.file_type = 'document'
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.file and self.file.storage.exists(self.file.name):
            self.file.delete(save=False)
        super().delete(*args, **kwargs)


class ForumTag(models.Model):
    """Tags for categorizing threads"""
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)
    color = models.CharField(max_length=7, default='#667eea')
    threads = models.ManyToManyField(ForumThread, related_name='tags', blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
