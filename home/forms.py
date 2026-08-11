from django import forms
from django.contrib.auth import get_user_model
from django.db import models

from .models import Article, ArticleComment, Question, Answer, Report, ReportComment, Tag


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data if d]
        else:
            result = [single_file_clean(data, initial)] if data else []
        return result


class ArticleForm(forms.ModelForm):
    parent = forms.ModelChoiceField(
        queryset=Article.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'kb-select'}),
        empty_label='Bottom section (no hierarchy)'
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'kb-select'})
    )
    attachments = MultipleFileField(
        required=False,
        label="Attachments",
        help_text="Upload supporting files (images, PDFs, docs)"
    )

    class Meta:
        model = Article
        fields = ['title', 'excerpt', 'content', 'category', 'parent', 'tags', 'is_hierarchy_root']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'kb-input', 'placeholder': 'Article title'}),
            'excerpt': forms.TextInput(attrs={'class': 'kb-input', 'placeholder': 'Short summary'}),
            'content': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 10, 'placeholder': 'Write the article content'}),
            'category': forms.Select(attrs={'class': 'kb-select'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        hierarchy_queryset = Article.objects.filter(
            models.Q(is_hierarchy_root=True) | models.Q(parent__isnull=False)
        ).order_by('title')
        if self.instance and self.instance.pk:
            hierarchy_queryset = hierarchy_queryset.exclude(pk=self.instance.pk)
        self.fields['parent'].queryset = hierarchy_queryset
        if not (user and user.is_staff):
            self.fields.pop('is_hierarchy_root', None)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('is_hierarchy_root') and cleaned_data.get('parent'):
            self.add_error('parent', 'Hierarchy roots cannot have a parent.')
        return cleaned_data


class QuestionForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'kb-select'})
    )
    tagged_users = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.filter(is_active=True).order_by('first_name', 'username'),
        required=False,
        label="Tag specific people",
        help_text="They'll get an email pointing them at this request.",
        widget=forms.SelectMultiple(attrs={'class': 'kb-select'})
    )
    already_solved = forms.BooleanField(
        required=False,
        label="I already solved this — share it as a learning post",
        help_text="Skip the open request stage and publish your problem + solution together."
    )
    solution = forms.CharField(
        required=False,
        label="Solution",
        widget=forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 6, 'placeholder': 'How did you solve it? Include the steps or fix so others can reuse it.'})
    )

    class Meta:
        model = Question
        fields = ['title', 'body', 'tags', 'tagged_users']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'kb-input', 'placeholder': 'What do you want to know?'}),
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 8, 'placeholder': 'Add context, code, or links'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ('tagged_users',):
            self.fields[field].label_from_instance = lambda user: user.get_full_name() or user.username

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('already_solved') and not cleaned_data.get('solution', '').strip():
            self.add_error('solution', 'Describe the solution, or uncheck "I already solved this".')
        return cleaned_data


class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 6, 'placeholder': 'Write your answer'}),
        }


class ReportForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'kb-select'})
    )
    attachments = MultipleFileField(
        required=False,
        label="Screenshots",
        help_text="Upload screenshots (PNG, JPG, GIF)"
    )

    class Meta:
        model = Report
        fields = ['type', 'title', 'description', 'application', 'assignee', 'priority', 'status', 'tags']
        widgets = {
            'type': forms.Select(attrs={'class': 'kb-select'}),
            'title': forms.TextInput(attrs={'class': 'kb-input', 'placeholder': 'Short, descriptive title'}),
            'description': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 8, 'placeholder': 'Describe the issue or request'}),
            'application': forms.Select(attrs={'class': 'kb-select'}),
            'assignee': forms.Select(attrs={'class': 'kb-select'}),
            'priority': forms.Select(attrs={'class': 'kb-select'}),
            'status': forms.Select(attrs={'class': 'kb-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'type' in self.fields:
            self.fields['type'].initial = Report.TYPE_BUG
        if 'status' in self.fields:
            self.fields['status'].initial = Report.STATUS_OPEN
        if 'priority' in self.fields:
            self.fields['priority'].initial = Report.PRIORITY_MEDIUM
        assignee_field = self.fields.get('assignee')
        if assignee_field:
            assignee_field.label_from_instance = (
                lambda user: user.get_full_name() or user.username
            )


class ReportCommentForm(forms.ModelForm):
    class Meta:
        model = ReportComment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 4, 'placeholder': 'Add a comment'}),
        }


class ArticleCommentForm(forms.ModelForm):
    class Meta:
        model = ArticleComment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 4, 'placeholder': 'Add a comment'}),
        }
