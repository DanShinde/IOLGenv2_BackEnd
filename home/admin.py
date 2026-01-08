from django.contrib import admin

from .models import (
    UserProfile,
    Application,
    Tag,
    Category,
    Article,
    Question,
    Answer,
    Report,
    ReportComment,
    ReportAttachment,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'reputation']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'department']


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'repository_url']
    search_fields = ['name', 'description', 'repository_url']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'parent', 'is_hierarchy_root', 'author', 'views', 'updated_at']
    list_filter = ['category', 'is_hierarchy_root', 'updated_at']
    search_fields = ['title', 'content', 'excerpt', 'author__username']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['views', 'created_at', 'updated_at']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'votes', 'is_solved', 'created_at']
    list_filter = ['is_solved', 'created_at']
    search_fields = ['title', 'body', 'author__username']


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['question', 'author', 'votes', 'is_accepted', 'created_at']
    list_filter = ['is_accepted', 'created_at']
    search_fields = ['body', 'author__username', 'question__title']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'type', 'application', 'priority', 'status', 'reporter', 'assignee', 'updated_at']
    list_filter = ['type', 'priority', 'status', 'application']
    search_fields = ['title', 'description', 'reporter__username', 'assignee__username']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']


@admin.register(ReportComment)
class ReportCommentAdmin(admin.ModelAdmin):
    list_display = ['report', 'author', 'created_at']
    search_fields = ['body', 'author__username', 'report__title']


@admin.register(ReportAttachment)
class ReportAttachmentAdmin(admin.ModelAdmin):
    list_display = ['report', 'uploaded_by', 'uploaded_at']
    search_fields = ['report__title', 'uploaded_by__username']
