from django import forms

from .models import BugReport


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Custom FileField that handles multiple file uploads."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


class BugReportForm(forms.ModelForm):
    screenshots = MultipleFileField(
        required=False,
        help_text="You can upload multiple screenshots (PNG, JPG, JPEG).",
    )

    class Meta:
        model = BugReport
        fields = [
            "title",
            "application_version",
            "log_text",
            "steps_to_reproduce",
            "current_status_details",
        ]
        widgets = {
            "log_text": forms.Textarea(attrs={"rows": 4}),
            "steps_to_reproduce": forms.Textarea(attrs={"rows": 4}),
            "current_status_details": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            existing_classes = field.widget.attrs.get("class", "")
            if name == "screenshots":
                field.widget.attrs["class"] = f"{existing_classes} form-control".strip()
            else:
                field.widget.attrs["class"] = f"{existing_classes} form-control".strip()

    def clean_screenshots(self):
        files = self.cleaned_data.get("screenshots", [])

        # Filter out None values (happens when no file is uploaded)
        files = [f for f in files if f is not None]

        if not files:
            return []

        for file in files:
            # Validate file type
            content_type = getattr(file, "content_type", "") or ""
            if content_type and not content_type.startswith("image/"):
                raise forms.ValidationError(
                    f"Only image files are allowed. '{file.name}' is not an image."
                )

            # Validate file size (max 5MB per file)
            max_size = 5 * 1024 * 1024  # 5MB
            if file.size > max_size:
                raise forms.ValidationError(
                    f"File '{file.name}' exceeds maximum size of 5MB."
                )

        return files


class BugReportStatusForm(forms.ModelForm):
    class Meta:
        model = BugReport
        fields = ["status", "current_status_details"]
        widgets = {
            "current_status_details": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            existing_classes = field.widget.attrs.get("class", "")
            if name == "status":
                field.widget.attrs["class"] = f"{existing_classes} form-select".strip()
            else:
                field.widget.attrs["class"] = f"{existing_classes} form-control".strip()
