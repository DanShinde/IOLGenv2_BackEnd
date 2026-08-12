from django import forms

from .models import Activity, ComplexityLevel, ModuleType, Project, Segment


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


class ProjectForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'customer', 'complexity', 'notes', 'minutes_per_working_day']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Acme Distribution Center - Phase 1'}),
            'customer': forms.TextInput(attrs={'placeholder': 'Optional customer name'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional notes'}),
            'minutes_per_working_day': forms.NumberInput(attrs={'min': '1'}),
        }
