from django import forms
from .models import RoleMatrix, SkillMatrix, EmployeeSkill, Skill, DevelopmentPlan

class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'

class SkillForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Skill
        fields = ['name', 'category', 'scope', 'segment', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Enter skill name'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional description'}),
        }

class RoleMatrixForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RoleMatrix
        fields = ['title', 'department', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g., Software Engineer'}),
            'department': forms.TextInput(attrs={'placeholder': 'e.g., Engineering'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional description'}),
        }

class DevelopmentPlanForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DevelopmentPlan
        fields = ['skill', 'action', 'resource_url', 'target_date', 'status', 'notes']
        widgets = {
            'action': forms.TextInput(attrs={'placeholder': "e.g. 'Complete Django REST course'"}),
            'resource_url': forms.URLInput(attrs={'placeholder': 'https://... (optional)'}),
            'target_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional notes'}),
        }

class SkillMatrixForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SkillMatrix
        fields = ['employee', 'role_matrix', 'manager', 'status', 'user', 'segments']
        labels = {
            'employee': 'Employee',
            'role_matrix': 'Designation',
            'manager': 'Manager (for self-rating approval)',
            'user': 'Linked Login (for self-service rating)',
            'segments': 'Segments (Ctrl/Cmd-click to select more than one)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # An employee can't be their own manager.
        if self.instance and self.instance.pk:
            self.fields['manager'].queryset = self.fields['manager'].queryset.exclude(pk=self.instance.pk)
        # An Employee can only be linked to one SkillMatrix row -- once assigned, don't offer
        # it again to a different SkillMatrix. On an edit, the current employee stays in the
        # dropdown alongside the still-unlinked ones.
        employee_qs = self.fields['employee'].queryset.filter(skill_matrix__isnull=True)
        if self.instance and self.instance.pk and self.instance.employee_id:
            employee_qs = employee_qs | self.fields['employee'].queryset.filter(pk=self.instance.employee_id)
        self.fields['employee'].queryset = employee_qs.order_by('name')

class EmployeeSkillForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = EmployeeSkill
        fields = ['skill_matrix', 'skill', 'actual_level', 'notes']
        labels = {
            'skill_matrix': 'Employee',
        }
        widgets = {
            'actual_level': forms.NumberInput(attrs={'min': 0, 'max': 5}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional notes'}),
        }

