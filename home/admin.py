from django.contrib import admin
from .models import (
    ForumCategory, ForumThread, ForumPost,
    ForumAttachment, ForumTag
)


@admin.register(ForumCategory)
class ForumCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon', 'color', 'order', 'is_active', 'thread_count', 'post_count']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['order', 'name']

    def thread_count(self, obj):
        return obj.thread_count
    thread_count.short_description = 'Threads'

    def post_count(self, obj):
        return obj.post_count
    post_count.short_description = 'Posts'


@admin.register(ForumThread)
class ForumThreadAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'author', 'status', 'priority', 'views', 'is_pinned', 'is_locked', 'created_at']
    list_filter = ['category', 'status', 'priority', 'is_pinned', 'is_locked', 'created_at']
    search_fields = ['title', 'content', 'author__username']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['views', 'created_at', 'updated_at', 'last_activity_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'title', 'slug', 'content', 'author')
        }),
        ('Bug Report Details', {
            'fields': ('application_version', 'steps_to_reproduce', 'log_text'),
            'classes': ('collapse',)
        }),
        ('Thread Settings', {
            'fields': ('status', 'priority', 'is_pinned', 'is_locked', 'best_answer')
        }),
        ('Statistics', {
            'fields': ('views', 'created_at', 'updated_at', 'last_activity_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = ['thread', 'author', 'created_at', 'upvote_count_display', 'is_solution', 'is_edited']
    list_filter = ['is_solution', 'is_edited', 'created_at']
    search_fields = ['content', 'author__username', 'thread__title']
    readonly_fields = ['created_at', 'updated_at', 'upvote_count_display']
    date_hierarchy = 'created_at'

    def upvote_count_display(self, obj):
        return obj.upvote_count
    upvote_count_display.short_description = 'Upvotes'


@admin.register(ForumAttachment)
class ForumAttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_name', 'thread', 'post', 'file_type', 'file_size_display', 'uploaded_by', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['original_name', 'thread__title']
    readonly_fields = ['uploaded_at', 'file_size']

    def file_size_display(self, obj):
        """Display file size in human-readable format"""
        size = obj.file_size
        for unit in ['B', 'KB', 'MB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"
    file_size_display.short_description = 'File Size'


@admin.register(ForumTag)
class ForumTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color', 'thread_count']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}

    def thread_count(self, obj):
        return obj.threads.count()
    thread_count.short_description = 'Threads'
