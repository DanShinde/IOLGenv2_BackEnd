# planner/forms.py

from django import forms
from employees.models import Employee
from .models import Project, Activity, Leave, Site, SiteAllocation

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['project_id', 'customer_name', 'segment', 'team_lead']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-input w-full px-4 py-3 rounded-lg border-2 border-gray-300 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 transition-all duration-200'
            })
        
        self.fields['project_id'].widget.attrs.update({
            'placeholder': 'Enter unique project code (e.g., PROJ-001)'
        })
        self.fields['customer_name'].widget.attrs.update({
            'placeholder': 'Enter client or customer name'
        })
        if 'team_lead' in self.fields:
            self.fields['team_lead'].empty_label = "Select a Team Lead"

class ActivityForm(forms.ModelForm):
    assignee = forms.ModelChoiceField(
        queryset=Employee.objects.all(),
        required=False
    )
    
    class Meta:
        model = Activity
        fields = [
            'project', 'activity_name', 'assignee', 
            'remark', 'start_date', 'duration'
        ]
        widgets = {
            'start_date': forms.DateInput(
                attrs={
                    'type': 'date'
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            common_classes = 'form-input mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500'
            current_classes = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{common_classes} {current_classes}'.strip()
            
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3

class LeaveForm(forms.ModelForm):
    class Meta:
        model = Leave
        fields = ['employee', 'start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply standard styling
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'form-input w-full px-3 py-2 text-xs rounded-lg border-2 border-gray-300 focus:border-indigo-500 focus:outline-none'
            })

class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ['project', 'name', 'location', 'is_office']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].empty_label = "Select Project Code"
        self.fields['name'].required = False
        self.fields['project'].required = False
        for field_name, field in self.fields.items():
            if field_name != 'is_office':
                field.widget.attrs.update({
                    'class': 'form-input w-full px-3 py-2 text-xs rounded-lg border-2 border-gray-300 focus:border-indigo-500 focus:outline-none'
                })
            else:
                field.widget.attrs.update({
                    'class': 'form-checkbox h-4 w-4 text-indigo-600 transition duration-150 ease-in-out'
                })

    def clean(self):
        cleaned_data = super().clean()
        is_office = cleaned_data.get('is_office')
        project = cleaned_data.get('project')
        name = cleaned_data.get('name')

        if is_office:
            if not name:
                self.add_error('name', 'Site Name is required for Office locations.')
            cleaned_data['project'] = None
        else:
            if not project:
                self.add_error('project', 'Project is required for Site locations.')
        return cleaned_data

class SiteAllocationForm(forms.ModelForm):
    class Meta:
        model = SiteAllocation
        fields = ['employee', 'site', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'form-input w-full px-3 py-2 text-xs rounded-lg border-2 border-gray-300 focus:border-indigo-500 focus:outline-none'
            })