from django import forms
from .models import ForumThread, ForumPost, ForumCategory, ForumTag


class MultipleFileInput(forms.ClearableFileInput):
    """Widget for multiple file uploads"""
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Custom FileField that handles multiple file uploads"""

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


class ThreadCreateForm(forms.ModelForm):
    """Form for creating new forum threads"""
    attachments = MultipleFileField(
        required=False,
        help_text="Upload screenshots or files (max 5MB each)",
        label="Attachments"
    )

    tags = forms.ModelMultipleChoiceField(
        queryset=ForumTag.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select relevant tags"
    )

    class Meta:
        model = ForumThread
        fields = [
            'category',
            'title',
            'content',
            'application_version',
            'steps_to_reproduce',
            'log_text',
            'priority',
        ]
        widgets = {
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all'
            }),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all',
                'placeholder': 'Brief, descriptive title...'
            }),
            'content': forms.Textarea(attrs={
                'rows': 6,
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all',
                'placeholder': 'Describe your issue, question, or idea in detail...'
            }),
            'application_version': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all',
                'placeholder': 'e.g., v2.0.1'
            }),
            'steps_to_reproduce': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all',
                'placeholder': '1. Go to...\n2. Click on...\n3. See error...'
            }),
            'log_text': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent font-mono text-sm bg-gray-50',
                'placeholder': 'Paste error logs or stack traces here...'
            }),
            'priority': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all'
            }),
        }

    def clean_attachments(self):
        """Validate uploaded files"""
        files = self.cleaned_data.get('attachments', [])
        files = [f for f in files if f is not None]

        if not files:
            return []

        for file in files:
            # Validate file size (max 5MB)
            max_size = 5 * 1024 * 1024
            if file.size > max_size:
                raise forms.ValidationError(
                    f"File '{file.name}' exceeds maximum size of 5MB."
                )

        return files


class ThreadUpdateForm(forms.ModelForm):
    """Form for updating thread status and details"""

    class Meta:
        model = ForumThread
        fields = ['status', 'priority', 'content']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all'
            }),
            'priority': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all'
            }),
            'content': forms.Textarea(attrs={
                'rows': 6,
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all'
            }),
        }


class PostCreateForm(forms.ModelForm):
    """Form for creating replies/posts"""
    attachments = MultipleFileField(
        required=False,
        help_text="Upload screenshots or files",
        label="Attachments"
    )

    class Meta:
        model = ForumPost
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all',
                'placeholder': 'Write your reply...'
            }),
        }
        labels = {
            'content': 'Your Reply'
        }

    def clean_attachments(self):
        """Validate uploaded files"""
        files = self.cleaned_data.get('attachments', [])
        files = [f for f in files if f is not None]

        if not files:
            return []

        for file in files:
            max_size = 5 * 1024 * 1024
            if file.size > max_size:
                raise forms.ValidationError(
                    f"File '{file.name}' exceeds maximum size of 5MB."
                )

        return files


class ThreadFilterForm(forms.Form):
    """Form for filtering threads"""
    category = forms.ModelChoiceField(
        queryset=ForumCategory.objects.filter(is_active=True),
        required=False,
        empty_label='All Categories',
        widget=forms.Select(attrs={
            'class': 'px-4 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 transition-all'
        })
    )

    status = forms.ChoiceField(
        choices=[('', 'All Status')] + ForumThread.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'px-4 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 transition-all'
        })
    )

    priority = forms.ChoiceField(
        choices=[('', 'All Priorities')] + ForumThread.PRIORITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'px-4 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 transition-all'
        })
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'px-4 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 transition-all',
            'placeholder': 'Search threads...'
        })
    )

    sort_by = forms.ChoiceField(
        choices=[
            ('recent', 'Recent Activity'),
            ('created', 'Newest First'),
            ('views', 'Most Viewed'),
            ('posts', 'Most Replies'),
        ],
        required=False,
        initial='recent',
        widget=forms.Select(attrs={
            'class': 'px-4 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 transition-all'
        })
    )
