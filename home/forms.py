from django import forms

from .models import Article, Question, Answer, Report, ReportComment, Tag


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
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'kb-select'})
    )

    class Meta:
        model = Article
        fields = ['title', 'excerpt', 'content', 'category', 'tags']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'kb-input', 'placeholder': 'Article title'}),
            'excerpt': forms.TextInput(attrs={'class': 'kb-input', 'placeholder': 'Short summary'}),
            'content': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 10, 'placeholder': 'Write the article content'}),
            'category': forms.Select(attrs={'class': 'kb-select'}),
        }


class QuestionForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'kb-select'})
    )

    class Meta:
        model = Question
        fields = ['title', 'body', 'tags']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'kb-input', 'placeholder': 'What do you want to know?'}),
            'body': forms.Textarea(attrs={'class': 'kb-textarea', 'rows': 8, 'placeholder': 'Add context, code, or links'}),
        }


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
