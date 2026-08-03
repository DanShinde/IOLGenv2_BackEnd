from django import forms
from .models import RoleMatrix, SkillBenchmark, SkillMatrix, EmployeeSkill, Skill, DevelopmentPlan

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
        fields = ['name', 'category', 'description']
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

class SkillBenchmarkForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SkillBenchmark
        fields = ['role_matrix', 'skill', 'required_level', 'is_mandatory']
        widgets = {
            'required_level': forms.NumberInput(attrs={'min': 0, 'max': 5}),
        }

class RoleMatrixBenchmarkForm(BootstrapFormMixin, forms.ModelForm):
    skill_name = forms.CharField(
        label='Skill Name',
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Enter or select skill name'})
    )
    skill_category = forms.ChoiceField(
        label='Category',
        required=False,
        choices=[('', 'Select Category')] + list(Skill.CATEGORY_CHOICES)
    )
    
    class Meta:
        model = SkillBenchmark
        fields = ['skill_name', 'skill_category', 'required_level']
        widgets = {
            'required_level': forms.NumberInput(attrs={'min': 0, 'max': 5, 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['skill_name'].widget.attrs['list'] = 'skill-suggestions'
        # Set field order
        self.order_fields(['skill_name', 'skill_category', 'required_level'])
    
    def clean(self):
        cleaned_data = super().clean()
        skill_name = cleaned_data.get('skill_name', '').strip()
        skill_category = cleaned_data.get('skill_category', '')
        
        if skill_name:
            skill, created = Skill.objects.get_or_create(
                name__iexact=skill_name,
                defaults={'name': skill_name, 'category': skill_category if skill_category else None}
            )
            cleaned_data['skill'] = skill
        
        return cleaned_data

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
        fields = ['employee', 'role_matrix', 'manager', 'status', 'user']
        labels = {
            'employee': 'Employee',
            'role_matrix': 'Designation',
            'manager': 'Manager (for self-rating approval)',
            'user': 'Linked Login (for self-service rating)',
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

