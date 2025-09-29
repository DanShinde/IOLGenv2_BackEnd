# planner/forms.py

from django import forms
from .models import Project, Activity, Employee

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        # --- MODIFIED ---
        # Removed 'name' from the fields list.
        fields = ['project_id', 'customer_name', 'segment', 'team_lead']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-input w-full px-4 py-3 rounded-lg border-2 border-gray-300 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 transition-all duration-200'
            })
        
        # Add specific placeholders
        self.fields['project_id'].widget.attrs.update({
            'placeholder': 'Enter unique project code (e.g., PROJ-001)'
        })
        # --- REMOVED ---
        # self.fields['name'].widget.attrs.update({
        #     'placeholder': 'Enter descriptive project name'
        # })
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