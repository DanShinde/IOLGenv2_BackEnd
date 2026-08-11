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


class TagsField(forms.CharField):
    """
    Free-form tags: the user types whatever they want, not a fixed preset
    list. Renders as a single text input (comma-separated) that a small JS
    widget upgrades into a chip editor with autocomplete over existing tag
    names -- but a plain comma-separated string still works with JS off.

    Not tied to the model's `tags` M2M directly (ModelForm's automatic
    save_m2m() can't map free-typed names to Tag rows), so this field is
    deliberately left out of every Meta.fields list. The view resolves the
    cleaned name list to Tag instances (get_or_create) and calls
    instance.tags.set(...) itself, the same way `attachments` is handled.
    """
    widget = forms.TextInput(attrs={
        'class': 'kb-tags-input',
        'placeholder': 'Type a tag and press Enter',
        'autocomplete': 'off',
    })

    MAX_TAG_LENGTH = 50

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', 'Tags')
        kwargs.setdefault('help_text', "Add as many as you like — press Enter after each one. Commas separate tags, so they can't appear inside a tag name.")
        super().__init__(*args, **kwargs)
        suggestions = ','.join(Tag.objects.order_by('name').values_list('name', flat=True))
        self.widget.attrs['data-suggestions'] = suggestions
        self.widget.attrs['maxlength'] = self.MAX_TAG_LENGTH

    def clean(self, value):
        if not value:
            if self.required:
                raise forms.ValidationError(self.error_messages['required'], code='required')
            return []

        seen = set()
        names = []
        oversized = []
        for raw in value.split(','):
            # A literal comma can never survive inside one tag -- it's the
            # delimiter between tags, both here and in the chip-input JS.
            name = raw.strip()
            if not name:
                continue
            if len(name) > self.MAX_TAG_LENGTH:
                oversized.append(name)
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(name)

        if oversized:
            raise forms.ValidationError(
                f"These tags are too long (max {self.MAX_TAG_LENGTH} characters): " + ', '.join(oversized)
            )
        return names

    def prepare_value(self, value):
        if not value:
            return ''
        if hasattr(value, 'all'):
            value = list(value.all())
        return ','.join(item.name if hasattr(item, 'name') else str(item) for item in value)


class UserTagField(forms.CharField):
    """
    Chip-input for tagging specific *existing* people (unlike TagsField,
    this can't invent new rows -- there's no such thing as a free-typed
    user). The widget stores comma-separated user IDs resolved client-side
    by the enhancer JS matching what was typed against real suggestions;
    clean() re-validates those IDs against the DB rather than trusting them.
    """
    widget = forms.TextInput(attrs={
        'class': 'kb-user-tags-input',
        'placeholder': 'Type a name…',
        'autocomplete': 'off',
    })

    def __init__(self, *args, queryset=None, **kwargs):
        kwargs.setdefault('required', False)
        super().__init__(*args, **kwargs)
        self.queryset = queryset if queryset is not None else get_user_model().objects.filter(is_active=True)
        import json
        suggestions = [
            {'id': u.pk, 'label': u.get_full_name() or u.username}
            for u in self.queryset.order_by('first_name', 'username')
        ]
        self.widget.attrs['data-suggestions'] = json.dumps(suggestions)

    def clean(self, value):
        if not value:
            if self.required:
                raise forms.ValidationError(self.error_messages['required'], code='required')
            return []
        ids = [int(part) for part in value.split(',') if part.strip().isdigit()]
        if not ids:
            return []
        users_by_id = {u.pk: u for u in self.queryset.filter(pk__in=ids)}
        # Preserve the order the chips were added in, silently drop any id
        # that no longer resolves (deactivated user, tampered value, etc.).
        return [users_by_id[i] for i in ids if i in users_by_id]

    def prepare_value(self, value):
        if not value:
            return ''
        if hasattr(value, 'all'):
            value = list(value.all())
        return ','.join(str(item.pk) for item in value)


class RichTextFormatField(forms.CharField):
    """
    Hidden companion to an optional-rich-text field: 'plain' unless the user
    switches on formatting, in which case JS flips it to 'html' so the view
    knows whether to sanitize-and-store-as-HTML or store as plain text.
    """
    widget = forms.HiddenInput()

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('required', False)
        kwargs.setdefault('initial', 'plain')
        super().__init__(*args, **kwargs)

    def clean(self, value):
        return 'html' if value == 'html' else 'plain'


class ArticleForm(forms.ModelForm):
    parent = forms.ModelChoiceField(
        queryset=Article.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'kb-select'}),
        empty_label='Bottom section (no hierarchy)'
    )
    tags = TagsField()
    attachments = MultipleFileField(
        required=False,
        label="Attachments",
        help_text="Upload supporting files (images, PDFs, docs)"
    )

    class Meta:
        model = Article
        fields = ['title', 'excerpt', 'content', 'category', 'parent', 'is_hierarchy_root']
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
            self.fields['tags'].initial = self.instance.tags.all()
        self.fields['parent'].queryset = hierarchy_queryset
        if not (user and user.is_staff):
            self.fields.pop('is_hierarchy_root', None)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('is_hierarchy_root') and cleaned_data.get('parent'):
            self.add_error('parent', 'Hierarchy roots cannot have a parent.')
        return cleaned_data


class QuestionForm(forms.ModelForm):
    tags = TagsField()
    tagged_users = UserTagField(
        label="Tag specific people",
        help_text="They'll get an email pointing them at this request.",
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
    solution_format = RichTextFormatField()
    body_format = RichTextFormatField()

    class Meta:
        model = Question
        fields = ['title', 'body']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'kb-input', 'placeholder': 'What do you want to know?'}),
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 8, 'placeholder': 'Add context, code, or links'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['tags'].initial = self.instance.tags.all()
            self.fields['tagged_users'].initial = self.instance.tagged_users.all()
            self.fields['body_format'].initial = 'html' if self.instance.is_html else 'plain'

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('already_solved') and not cleaned_data.get('solution', '').strip():
            self.add_error('solution', 'Describe the solution, or uncheck "I already solved this".')
        return cleaned_data


class AnswerForm(forms.ModelForm):
    body_format = RichTextFormatField()

    class Meta:
        model = Answer
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 6, 'placeholder': 'Share your solution, workaround, or relevant info'}),
        }


class ReportForm(forms.ModelForm):
    tags = TagsField()
    attachments = MultipleFileField(
        required=False,
        label="Screenshots",
        help_text="Upload screenshots (PNG, JPG, GIF)"
    )
    description_format = RichTextFormatField()

    class Meta:
        model = Report
        fields = ['type', 'title', 'description', 'application', 'assignee', 'priority', 'status']
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
        if self.instance and self.instance.pk:
            self.fields['tags'].initial = self.instance.tags.all()
            self.fields['description_format'].initial = 'html' if self.instance.description_is_html else 'plain'


class ReportCommentForm(forms.ModelForm):
    body_format = RichTextFormatField()

    class Meta:
        model = ReportComment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 4, 'placeholder': 'Add a comment'}),
        }


class ArticleCommentForm(forms.ModelForm):
    body_format = RichTextFormatField()

    class Meta:
        model = ArticleComment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 4, 'placeholder': 'Add a comment'}),
        }
