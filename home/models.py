from django.conf import settings
from django.db import models
from ckeditor_uploader.fields import RichTextUploadingField
from django.urls import reverse
from django.utils.text import slugify


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='home_profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(blank=True)
    department = models.CharField(max_length=100, blank=True)
    reputation = models.IntegerField(default=0)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Application(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    repository_url = models.URLField(blank=True)
    maintainers = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='maintained_apps', blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)
    color = models.CharField(max_length=7, default='#6366f1')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Article(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    content = RichTextUploadingField()
    excerpt = models.CharField(max_length=500, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='articles')
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children'
    )
    is_hierarchy_root = models.BooleanField(default=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='articles')
    tags = models.ManyToManyField(Tag, blank=True, related_name='articles')
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Article.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('kb-article-detail', kwargs={'slug': self.slug})


class ArticleRevision(models.Model):
    """Snapshot of an Article's content taken immediately before an edit overwrites it."""
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='revisions')
    title = models.CharField(max_length=200)
    content = RichTextUploadingField()
    excerpt = models.CharField(max_length=500, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='article_revisions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Revision of '{self.title}' at {self.created_at:%Y-%m-%d %H:%M}"


class ArticleComment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='article_comments')
    body = models.TextField()
    is_html = models.BooleanField(default=False, help_text="Whether body holds sanitized rich-text HTML rather than plain text.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author}"


def article_attachment_upload_to(instance, filename):
    return f"articles/{instance.article_id}/{filename}"


ARTICLE_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}


class ArticleAttachment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=article_attachment_upload_to)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='article_uploads'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.file.name

    @property
    def is_image(self):
        name = self.file.name.lower()
        return any(name.endswith(ext) for ext in ARTICLE_IMAGE_EXTENSIONS)

    @property
    def filename(self):
        return self.file.name.rsplit('/', 1)[-1]


class Question(models.Model):
    title = models.CharField(max_length=300)
    body = models.TextField()
    is_html = models.BooleanField(default=False, help_text="Whether body holds sanitized rich-text HTML rather than plain text.")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='questions')
    votes = models.IntegerField(default=0)
    is_solved = models.BooleanField(default=False)
    accepted_answer = models.ForeignKey(
        'Answer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_for'
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='questions')
    tagged_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='tagged_questions',
        help_text="People specifically flagged to help with this request."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('kb-question-detail', kwargs={'pk': self.pk})


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    body = models.TextField()
    is_html = models.BooleanField(default=False, help_text="Whether body holds sanitized rich-text HTML rather than plain text.")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='answers')
    votes = models.IntegerField(default=0)
    is_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Answer by {self.author}"


class Vote(models.Model):
    UP = 1
    DOWN = -1
    VALUE_CHOICES = [(UP, 'Up'), (DOWN, 'Down')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='kb_votes')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, null=True, blank=True, related_name='user_votes')
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, null=True, blank=True, related_name='user_votes')
    value = models.SmallIntegerField(choices=VALUE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'question'],
                condition=models.Q(question__isnull=False),
                name='unique_user_question_vote',
            ),
            models.UniqueConstraint(
                fields=['user', 'answer'],
                condition=models.Q(answer__isnull=False),
                name='unique_user_answer_vote',
            ),
        ]

    def __str__(self):
        return f"{self.user} voted {self.value} on {self.question_id or self.answer_id}"


class Report(models.Model):
    TYPE_BUG = 'bug'
    TYPE_FEATURE = 'feature'
    TYPE_CHOICES = [
        (TYPE_BUG, 'Bug'),
        (TYPE_FEATURE, 'Feature'),
    ]

    PRIORITY_CRITICAL = 'critical'
    PRIORITY_HIGH = 'high'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_LOW = 'low'
    PRIORITY_CHOICES = [
        (PRIORITY_CRITICAL, 'Critical'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_LOW, 'Low'),
    ]

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

    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    title = models.CharField(max_length=300)
    description = models.TextField()
    description_is_html = models.BooleanField(default=False, help_text="Whether description holds sanitized rich-text HTML rather than plain text.")
    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name='reports')
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reported_items')
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='home_assigned_items'
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_OPEN)
    tags = models.ManyToManyField(Tag, blank=True, related_name='reports')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('kb-report-detail', kwargs={'pk': self.pk})


class ReportComment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='report_comments')
    body = models.TextField()
    is_html = models.BooleanField(default=False, help_text="Whether body holds sanitized rich-text HTML rather than plain text.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author}"


def report_attachment_upload_to(instance, filename):
    return f"reports/{instance.report_id}/{filename}"


class ReportAttachment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=report_attachment_upload_to)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='report_uploads'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.file.name
