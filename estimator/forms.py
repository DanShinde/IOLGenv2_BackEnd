from django import forms

from .models import Activity, ComplexityLevel, ModuleType, Project, ProjectTemplate, Segment


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'


class ActivityForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Activity
        fields = ['name', 'category', 'description', 'display_order']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Programming'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional description'}),
        }


class ModuleTypeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ModuleType
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Transfer Conveyor'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional description'}),
        }


class SegmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Segment
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Case Handling'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional description'}),
        }


class ComplexityLevelForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ComplexityLevel
        fields = ['name', 'multiplier', 'display_order']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Medium'}),
            'multiplier': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
        }


class UniqueNameFormMixin:
    """Case-insensitive uniqueness check on `name`, scoped to this form's own model only
    (a Project and a ProjectTemplate are allowed to share a name -- they're different
    kinds of things with their own separate naming pools)."""

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        qs = self._meta.model.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'A {self._meta.model._meta.verbose_name} named "{name}" already exists. Names must be unique.')
        return name


class ProjectForm(UniqueNameFormMixin, BootstrapFormMixin, forms.ModelForm):
    start_from_template = forms.ModelChoiceField(
        queryset=ProjectTemplate.objects.order_by('name'), required=False, label='Start from Template',
        help_text="Optional. Pre-fills the module rows below from this template once the project is created.",
    )

    class Meta:
        model = Project
        fields = ['name', 'customer', 'complexity', 'notes', 'minutes_per_working_day']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Acme Distribution Center - Phase 1'}),
            'customer': forms.TextInput(attrs={'placeholder': 'Optional customer name'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional notes'}),
            'minutes_per_working_day': forms.NumberInput(attrs={'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only offered on create -- an existing project already has its own modules, so
        # "start from template" wouldn't mean anything on the edit form.
        if self.instance.pk:
            del self.fields['start_from_template']
        else:
            self.order_fields(['name', 'customer', 'complexity', 'notes', 'minutes_per_working_day', 'start_from_template'])


class ProjectTemplateForm(UniqueNameFormMixin, BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectTemplate
        fields = ['name', 'description', 'complexity', 'minutes_per_working_day']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Standard Case Handling Cell'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional description'}),
            'minutes_per_working_day': forms.NumberInput(attrs={'min': '1'}),
        }


class SaveProjectAsTemplateForm(UniqueNameFormMixin, BootstrapFormMixin, forms.ModelForm):
    """Same fields as ProjectTemplateForm, used specifically for the 'Save as Template'
    flow off an existing project -- kept as its own form so the view can set a sensible
    default name without touching ProjectTemplateForm's plain-create behaviour."""

    class Meta:
        model = ProjectTemplate
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Standard Case Handling Cell'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional description'}),
        }
