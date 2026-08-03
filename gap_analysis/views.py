from collections import defaultdict
from datetime import date

from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy, reverse
from django.views.generic import TemplateView, DetailView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden
import json

from .forms import (
    RoleMatrixForm, SkillBenchmarkForm, SkillMatrixForm, EmployeeSkillForm, SkillForm,
    RoleMatrixBenchmarkForm, DevelopmentPlanForm,
)
from .mixins import StaffRequiredMixin
from .models import (
    RoleMatrix, SkillBenchmark, SkillMatrix, EmployeeSkill, Skill, DevelopmentPlan,
    gap_weight, user_can_manage_employee,
)
from .reports import build_team_report_data
from .exports import render_team_report_excel, render_team_report_pdf


def safe_json(data):
    """json.dumps() with <, >, & escaped, for embedding directly inside a <script> tag.

    Without this, a skill or employee name containing the literal text "</script>" would
    close the surrounding script block early (the HTML parser looks for that sequence
    regardless of JS string context), which is a stored-XSS vector since skill/employee
    names are free text. Mirrors what Django's own `json_script` template filter does.
    """
    return json.dumps(data).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'gap_analysis/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request

        employees = SkillMatrix.objects.all()
        designations = RoleMatrix.objects.prefetch_related('benchmarks').all()

        selected_emp_id = request.GET.get('employee')
        selected_desig_id = request.GET.get('designation')

        selected_employee = None
        if selected_emp_id:
            selected_employee = SkillMatrix.objects.filter(id=selected_emp_id).select_related('role_matrix').prefetch_related('skills', 'skills__skill').first()
        elif employees.exists():
            selected_employee = employees.select_related('role_matrix').prefetch_related('skills', 'skills__skill').first()

        selected_designation = None
        if selected_desig_id:
            selected_designation = RoleMatrix.objects.filter(id=selected_desig_id).first()
        elif designations.exists():
            selected_designation = designations.first()

        # One query for every benchmark, keyed by (role_id, skill_id) so nothing below
        # has to hit the database per employee-skill pair.
        benchmark_map = {
            (b.role_matrix_id, b.skill_id): b
            for b in SkillBenchmark.objects.select_related('skill').all()
        }

        def benchmark_for(role_matrix_id, skill_id):
            return benchmark_map.get((role_matrix_id, skill_id))

        # One query for every recorded skill level, reused for every section below
        # instead of each section re-querying EmployeeSkill from scratch.
        all_es = list(
            EmployeeSkill.objects.filter(skill__isnull=False)
            .select_related('skill_matrix__role_matrix', 'skill')
        )

        # 1. INDIVIDUAL DATA
        ind_labels, ind_actual, ind_benchmark = [], [], []
        if selected_employee:
            for es in selected_employee.skills.all():
                if es.skill_id is None:
                    continue
                bm = benchmark_for(selected_employee.role_matrix_id, es.skill_id)
                ind_labels.append(es.skill.name)
                ind_actual.append(es.actual_level)
                ind_benchmark.append(bm.required_level if bm else 0)

        # Single pass over all employee-skill rows, building every per-skill,
        # per-employee, and per-role aggregate at once.
        team_stats = defaultdict(lambda: {'actual_total': 0, 'benchmark_total': 0, 'count': 0})
        desig_stats = defaultdict(lambda: {'actual_total': 0, 'count': 0})
        role_gap_totals = defaultdict(lambda: {'weighted_gap': 0, 'weight': 0, 'employees': set()})
        emp_gap_totals = defaultdict(lambda: {'total_gap': 0, 'gap_count': 0})
        emp_critical = defaultdict(lambda: {'count': 0, 'skills': []})
        emp_performance = defaultdict(lambda: {'exceed_count': 0, 'total_evaluated': 0})
        emp_compliance = defaultdict(lambda: {'met_count': 0, 'gap_count': 0})
        skill_gap_totals = defaultdict(lambda: {'total_gap': 0, 'count': 0, 'category': None})

        total_weighted_gap = 0
        total_weight = 0
        skills_comparison_count = 0
        skills_met_count = 0

        for es in all_es:
            skill_name = es.skill.name
            emp = es.skill_matrix
            role_id = emp.role_matrix_id

            team_stats[skill_name]['actual_total'] += es.actual_level
            team_stats[skill_name]['count'] += 1

            if selected_designation and role_id == selected_designation.id:
                desig_stats[skill_name]['actual_total'] += es.actual_level
                desig_stats[skill_name]['count'] += 1

            bm = benchmark_for(role_id, es.skill_id)
            if bm is None:
                continue

            team_stats[skill_name]['benchmark_total'] += bm.required_level

            gap = bm.required_level - es.actual_level
            weight = gap_weight(bm.is_mandatory)

            total_weighted_gap += gap * weight
            total_weight += weight
            skills_comparison_count += 1
            if gap <= 0:
                skills_met_count += 1

            role_gap_totals[role_id]['weighted_gap'] += gap * weight
            role_gap_totals[role_id]['weight'] += weight
            role_gap_totals[role_id]['employees'].add(emp.id)

            if gap > 0:
                emp_gap_totals[emp.id]['total_gap'] += gap
                emp_gap_totals[emp.id]['gap_count'] += 1

                skill_gap_totals[skill_name]['total_gap'] += gap
                skill_gap_totals[skill_name]['count'] += 1
                skill_gap_totals[skill_name]['category'] = es.skill.category

            if gap > 2:
                emp_critical[emp.id]['count'] += 1
                emp_critical[emp.id]['skills'].append(skill_name)

            emp_performance[emp.id]['total_evaluated'] += 1
            if es.actual_level >= bm.required_level:
                emp_performance[emp.id]['exceed_count'] += 1
                emp_compliance[emp.id]['met_count'] += 1
            elif gap > 1:
                emp_compliance[emp.id]['gap_count'] += 1

        team_labels = list(team_stats.keys())
        team_actual = [round(team_stats[s]['actual_total'] / team_stats[s]['count'], 1) for s in team_labels]
        team_benchmark = [round(team_stats[s]['benchmark_total'] / team_stats[s]['count'], 1) for s in team_labels]

        # 3. DESIGNATION DATA
        desig_labels, desig_actual, desig_benchmark = [], [], []
        if selected_designation:
            desig_labels = list(desig_stats.keys())
            desig_actual = [round(desig_stats[s]['actual_total'] / desig_stats[s]['count'], 1) for s in desig_labels]
            role_benchmarks_by_skill_name = {
                b.skill.name: b.required_level
                for (role_id, _), b in benchmark_map.items() if role_id == selected_designation.id
            }
            desig_benchmark = [role_benchmarks_by_skill_name.get(label, 0) for label in desig_labels]

        # KPI Metrics
        total_employees = employees.count()
        total_skills = Skill.objects.count()

        avg_gap_score = round(total_weighted_gap / total_weight, 1) if total_weight > 0 else 0
        skills_met_percent = round((skills_met_count / skills_comparison_count) * 100) if skills_comparison_count > 0 else 0

        emp_by_id = {emp.id: emp for emp in employees}

        # 1. Role Gap Summary - weighted average gap per role
        role_gap_data = []
        for role in designations:
            totals = role_gap_totals.get(role.id)
            if not totals or totals['weight'] == 0:
                continue
            role_gap_data.append({
                'role': role.title,
                'department': role.department or '-',
                'avg_gap': round(totals['weighted_gap'] / totals['weight'], 2),
                'employee_count': len(totals['employees']),
            })

        # 2. Top Skill Gaps - employees with highest total gaps
        top_gap_employees = [
            {
                'name': emp_by_id[emp_id].name,
                'role': emp_by_id[emp_id].role_matrix.title if emp_by_id[emp_id].role_matrix else '-',
                'total_gap': totals['total_gap'],
                'gap_count': totals['gap_count'],
            }
            for emp_id, totals in emp_gap_totals.items()
        ]
        top_gap_employees = sorted(top_gap_employees, key=lambda x: x['total_gap'], reverse=True)[:5]

        # 3. Critical Gaps - employees with gap > 2
        critical_gaps = [
            {
                'name': emp_by_id[emp_id].name,
                'role': emp_by_id[emp_id].role_matrix.title if emp_by_id[emp_id].role_matrix else '-',
                'critical_count': data['count'],
                'skills': data['skills'][:3],
            }
            for emp_id, data in emp_critical.items()
        ]
        critical_gaps = sorted(critical_gaps, key=lambda x: x['critical_count'], reverse=True)[:5]

        # 4. Top Performers - employees exceeding benchmark requirements
        top_performers = [
            {
                'name': emp_by_id[emp_id].name,
                'role': emp_by_id[emp_id].role_matrix.title if emp_by_id[emp_id].role_matrix else '-',
                'exceed_count': data['exceed_count'],
                'total_evaluated': data['total_evaluated'],
                'exceed_percent': round((data['exceed_count'] / data['total_evaluated']) * 100),
            }
            for emp_id, data in emp_performance.items()
            if data['total_evaluated'] > 0
        ]
        top_performers = sorted(top_performers, key=lambda x: x['exceed_percent'], reverse=True)[:5]

        # 5. Skills Needing Training - skills with highest gaps across org
        skills_needing_training = [
            {
                'skill': skill_name,
                'category': data['category'] or '-',
                'avg_gap': round(data['total_gap'] / data['count'], 2),
                'affected_count': data['count'],
            }
            for skill_name, data in skill_gap_totals.items()
        ]
        skills_needing_training = sorted(skills_needing_training, key=lambda x: x['avg_gap'], reverse=True)[:5]

        # 6. Benchmark Compliance - % of employees meeting benchmarks
        compliance_stats = {'meeting': 0, 'partial': 0, 'needs_training': 0, 'total': 0}
        for emp_id, data in emp_compliance.items():
            compliance_stats['total'] += 1
            if data['met_count'] == 0 and data['gap_count'] > 0:
                compliance_stats['needs_training'] += 1
            elif data['met_count'] > 0 and data['gap_count'] == 0:
                compliance_stats['meeting'] += 1
            else:
                compliance_stats['partial'] += 1

        if compliance_stats['total'] > 0:
            compliance_stats['meeting_pct'] = round((compliance_stats['meeting'] / compliance_stats['total']) * 100)
            compliance_stats['partial_pct'] = round((compliance_stats['partial'] / compliance_stats['total']) * 100)
            compliance_stats['needs_training_pct'] = round((compliance_stats['needs_training'] / compliance_stats['total']) * 100)
        else:
            compliance_stats['meeting_pct'] = 0
            compliance_stats['partial_pct'] = 0
            compliance_stats['needs_training_pct'] = 0

        # 7. Skill Distribution by Category
        skill_category_dist = {}
        for cat in Skill.CATEGORY_CHOICES:
            count = Skill.objects.filter(category=cat[0]).count()
            if count > 0:
                skill_category_dist[cat[1]] = count
        skill_category_dist['Uncategorized'] = Skill.objects.filter(category__isnull=True).count()

        context.update({
            'employees': employees,
            'selected_employee': selected_employee,
            'designations': designations,
            'selected_designation': selected_designation,
            'ind_labels': safe_json(ind_labels),
            'ind_actual': safe_json(ind_actual),
            'ind_benchmark': safe_json(ind_benchmark),
            'team_labels': safe_json(team_labels),
            'team_actual': safe_json(team_actual),
            'team_benchmark': safe_json(team_benchmark),
            'desig_labels': safe_json(desig_labels),
            'desig_actual': safe_json(desig_actual),
            'desig_benchmark': safe_json(desig_benchmark),
            'total_employees': total_employees,
            'total_skills': total_skills,
            'avg_gap_score': avg_gap_score,
            'skills_met': skills_met_percent,
            # New insights
            'role_gap_data': role_gap_data,
            'top_gap_employees': top_gap_employees,
            'critical_gaps': critical_gaps,
            'top_performers': top_performers,
            'skills_needing_training': skills_needing_training,
            'compliance_stats': compliance_stats,
            'skill_category_dist': skill_category_dist,
        })
        return context

class SkillMatrixCardView(LoginRequiredMixin, DetailView):
    model = SkillMatrix
    template_name = 'gap_analysis/employee_card.html'
    pk_url_kwarg = 'emp_id'
    context_object_name = 'employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object
        
        benchmarks = SkillBenchmark.objects.filter(role_matrix=employee.role_matrix).select_related('skill')
        
        skill_details = []
        for bm in benchmarks:
            emp_skill = EmployeeSkill.objects.filter(skill_matrix=employee, skill=bm.skill).first()
            actual_level = emp_skill.actual_level if emp_skill else 0
            gap = bm.required_level - actual_level
            level_percentage = (actual_level / 5) * 100
            
            if gap <= 0:
                status = 'proficient'
            elif gap <= 1:
                status = 'warning'
            else:
                status = 'gap'
                
            skill_details.append({
                'name': bm.skill.name,
                'actual': actual_level,
                'level_percentage': level_percentage,
                'required': bm.required_level,
                'gap': gap,
                'status': status,
            })
            
        context['skill_details'] = skill_details

        if skill_details:
            proficient_count = sum(1 for s in skill_details if s['gap'] <= 0)
            skills_met_pct = round((proficient_count / len(skill_details)) * 100)
        else:
            skills_met_pct = 0
        context['skills_met_pct'] = skills_met_pct

        context['development_plans'] = employee.development_plans.select_related('skill').all()

        return context

# --- CREATE VIEWS ---
class RoleMatrixCreateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = RoleMatrix
    form_class = RoleMatrixForm
    template_name = 'gap_analysis/add_form.html'
    success_url = reverse_lazy('skillgap_dashboard')
    success_message = "RoleMatrix created successfully!"
    extra_context = {'title': 'Add RoleMatrix'}

class SkillBenchmarkCreateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = SkillBenchmark
    form_class = SkillBenchmarkForm
    template_name = 'gap_analysis/add_form.html'
    success_url = reverse_lazy('skillgap_dashboard')
    success_message = "Skill benchmark created successfully!"
    extra_context = {'title': 'Add Skill Benchmark'}

class SkillMatrixCreateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = SkillMatrix
    form_class = SkillMatrixForm
    template_name = 'gap_analysis/add_form.html'
    success_url = reverse_lazy('skillgap_dashboard')
    success_message = "Skill Matrix created successfully!"
    extra_context = {'title': 'Add Employee'}

class EmployeeSkillCreateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = EmployeeSkill
    form_class = EmployeeSkillForm
    template_name = 'gap_analysis/add_form.html'
    success_url = reverse_lazy('skillgap_dashboard')
    success_message = "Employee skill recorded successfully!"
    extra_context = {'title': 'Add Employee Skill'}

class SkillCreateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Skill
    form_class = SkillForm
    template_name = 'gap_analysis/add_form.html'
    success_url = reverse_lazy('skillgap_dashboard')
    success_message = "Skill created successfully!"
    extra_context = {'title': 'Add Skill'}

# --- SKILL CRUD VIEWS ---
class SkillListView(LoginRequiredMixin, ListView):
    model = Skill
    template_name = 'gap_analysis/skill_list.html'
    context_object_name = 'skills'
    ordering = ['name']
    paginate_by = 15

class SkillUpdateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Skill
    form_class = SkillForm
    template_name = 'gap_analysis/add_form.html'
    success_url = reverse_lazy('skillgap_skill_list')
    success_message = "Skill updated successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Skill: {self.object.name}'
        return context

class SkillDeleteView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Skill
    template_name = 'gap_analysis/skill_confirm_delete.html'
    success_url = reverse_lazy('skillgap_skill_list')
    success_message = "Skill deleted successfully!"

# --- EMPLOYEE CRUD VIEWS ---
class SkillMatrixListView(LoginRequiredMixin, ListView):
    model = SkillMatrix
    template_name = 'gap_analysis/employee_list.html'
    context_object_name = 'employees'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = SkillMatrix.objects.select_related('role_matrix', 'employee').prefetch_related('skills').order_by('employee__name')
        
        # Apply filters
        designation_filter = self.request.GET.get('designation')
        status_filter = self.request.GET.get('status')
        
        if designation_filter:
            queryset = queryset.filter(role_matrix_id=designation_filter)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['designations'] = RoleMatrix.objects.all()
        context['selected_designation'] = self.request.GET.get('designation')
        context['selected_status'] = self.request.GET.get('status')
        return context


@login_required
def employee_export_csv(request):
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="employees.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Name', 'Email', 'Designation', 'Status', 'Total Skills', 'Avg Gap', 'Skills Met %'])
    
    employees = SkillMatrix.objects.select_related('role_matrix').prefetch_related('skills')
    
    designation_filter = request.GET.get('designation')
    status_filter = request.GET.get('status')
    
    if designation_filter:
        employees = employees.filter(role_matrix_id=designation_filter)
    if status_filter:
        employees = employees.filter(status=status_filter)
    
    for emp in employees:
        gap_data = emp.get_skill_gap_data()
        avg_gap = emp.get_overall_gap_score()
        skills_met = emp.get_skills_met_percentage()
        
        writer.writerow([
            emp.name,
            emp.email or '',
            emp.role_matrix.title if emp.role_matrix else '',
            emp.status,
            len(gap_data),
            round(avg_gap, 1),
            f"{skills_met}%"
        ])

    return response


@login_required
def team_report_excel(request):
    """Staff-only: whole-team skill matrix + dashboard, as a downloadable .xlsx."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff access required.")
    report_data = build_team_report_data(SkillMatrix.objects.all())
    return render_team_report_excel(report_data)


@login_required
def team_report_pdf(request):
    """Staff-only: whole-team skill matrix + dashboard, as a downloadable .pdf."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff access required.")
    report_data = build_team_report_data(SkillMatrix.objects.all())
    return render_team_report_pdf(report_data)


class BulkSkillUpdateView(LoginRequiredMixin, StaffRequiredMixin, TemplateView):
    template_name = 'gap_analysis/bulk_skill_update.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['employees'] = SkillMatrix.objects.select_related('role_matrix', 'employee').prefetch_related('skills', 'skills__skill').order_by('employee__name')
        context['skills'] = Skill.objects.all().order_by('name')
        return context
    
    def post(self, request):
        employee_ids = request.POST.getlist('employee_ids')
        skill_id = request.POST.get('skill_id')
        try:
            actual_level = int(request.POST.get('actual_level', 0))
        except (TypeError, ValueError):
            messages.error(request, "Skill level must be a number between 0 and 5.")
            return redirect('bulk_skill_update')

        if employee_ids and skill_id:
            skill = get_object_or_404(Skill, id=skill_id)
            employees = SkillMatrix.objects.filter(id__in=employee_ids)
            
            for emp in employees:
                EmployeeSkill.objects.update_or_create(
                    skill_matrix=emp,
                    skill=skill,
                    defaults={'actual_level': actual_level}
                )
            
            messages.success(request, f"Updated {len(employee_ids)} employee's skill level for {skill.name}")
        
        return redirect('bulk_skill_update')

class SkillMatrixUpdateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = SkillMatrix
    form_class = SkillMatrixForm
    template_name = 'gap_analysis/add_form.html'
    success_url = reverse_lazy('skillgap_employee_list')
    success_message = "Employee updated successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Employee: {self.object.name}'
        return context

class SkillMatrixDeleteView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, DeleteView):
    model = SkillMatrix
    template_name = 'gap_analysis/employee_confirm_delete.html'
    success_url = reverse_lazy('skillgap_employee_list')
    success_message = "Employee deleted successfully!"

# --- DESIGNATION CRUD VIEWS ---
class RoleMatrixListView(LoginRequiredMixin, ListView):
    model = RoleMatrix
    template_name = 'gap_analysis/designation_list.html'
    context_object_name = 'designations'
    ordering = ['title']
    paginate_by = 10

    def get_queryset(self):
        return super().get_queryset().prefetch_related('benchmarks')

class RoleMatrixUpdateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = RoleMatrix
    form_class = RoleMatrixForm
    template_name = 'gap_analysis/add_form.html'
    success_url = reverse_lazy('skillgap_designation_list')
    success_message = "RoleMatrix updated successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit RoleMatrix: {self.object.title}'
        return context

class RoleMatrixDeleteView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, DeleteView):
    model = RoleMatrix
    template_name = 'gap_analysis/designation_confirm_delete.html'
    success_url = reverse_lazy('skillgap_designation_list')
    success_message = "RoleMatrix deleted successfully!"

# --- BENCHMARK & EMPLOYEE SKILL LIST VIEWS ---
class BenchmarkListView(LoginRequiredMixin, ListView):
    model = SkillBenchmark
    template_name = 'gap_analysis/benchmark_list.html'
    context_object_name = 'benchmarks'
    queryset = SkillBenchmark.objects.select_related('role_matrix', 'skill').all()

class BenchmarkDeleteView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, DeleteView):
    model = SkillBenchmark
    template_name = 'gap_analysis/benchmark_confirm_delete.html'
    success_message = "Benchmark deleted successfully!"

    def get_success_url(self):
        return reverse('skillgap_designation_benchmark', kwargs={'pk': self.object.role_matrix.pk})

class EmployeeSkillListView(LoginRequiredMixin, ListView):
    model = EmployeeSkill
    template_name = 'gap_analysis/employee_skill_list.html'
    context_object_name = 'employee_skills'
    queryset = EmployeeSkill.objects.select_related('skill_matrix', 'skill').all().order_by('-last_evaluated')

class EmployeeSkillDeleteView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, DeleteView):
    model = EmployeeSkill
    template_name = 'gap_analysis/employee_skill_confirm_delete.html'
    success_url = reverse_lazy('skillgap_dashboard')
    success_message = "Employee skill deleted successfully!"

# --- EMPLOYEE PROFILE VIEWS ---
class SkillMatrixProfileView(LoginRequiredMixin, DetailView):
    model = SkillMatrix
    template_name = 'gap_analysis/employee_profile.html'
    pk_url_kwarg = 'pk'
    context_object_name = 'employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object
        
        benchmarks = employee.get_required_benchmarks()
        
        skill_data = []
        for benchmark in benchmarks:
            emp_skill = EmployeeSkill.objects.filter(skill_matrix=employee, skill=benchmark.skill).first()
            actual_level = emp_skill.actual_level if emp_skill else 0
            gap = benchmark.required_level - actual_level
            level_percentage = (actual_level / 5) * 100  # Convert 0-5 to percentage
            
            skill_data.append({
                'benchmark_id': benchmark.id,
                'skill_id': benchmark.skill.id,
                'skill_name': benchmark.skill.name,
                'skill_category': benchmark.skill.category,
                'required_level': benchmark.required_level,
                'actual_level': actual_level,
                'level_percentage': level_percentage,
                'gap': gap,
                'status': 'met' if gap <= 0 else ('warning' if gap <= 1 else 'critical'),
                'is_mandatory': benchmark.is_mandatory,
                'emp_skill_id': emp_skill.id if emp_skill else None,
                'self_rated_level': emp_skill.self_rated_level if emp_skill else None,
                'rating_status': emp_skill.rating_status if emp_skill else 'none',
                'rating_gap': emp_skill.rating_gap if emp_skill else None,
                'has_active_development_plan': emp_skill.has_active_development_plan if emp_skill else False,
            })
        
        # Sort by gap (critical first)
        skill_data.sort(key=lambda x: (0 if x['gap'] > 0 else 1, -x['gap']))
        
        context['skill_data'] = skill_data
        context['skills_met'] = employee.get_skills_met_percentage()
        context['overall_gap'] = employee.get_overall_gap_score()
        
        # Chart data
        context['chart_labels'] = safe_json([s['skill_name'] for s in skill_data])
        context['chart_actual'] = safe_json([s['actual_level'] for s in skill_data])
        context['chart_required'] = safe_json([s['required_level'] for s in skill_data])

        context['skill_history'] = safe_json(employee.get_skill_history())
        context['development_plans'] = employee.development_plans.select_related('skill')
        context['can_rate_employee'] = user_can_manage_employee(self.request.user, employee)
        context['is_own_profile'] = employee.user_id == self.request.user.id

        return context


@login_required
def employee_skill_update(request, pk):
    """AJAX view for a manager (staff, or this employee's manager) to set the official skill level"""
    skill_matrix = get_object_or_404(SkillMatrix, pk=pk)
    if not user_can_manage_employee(request.user, skill_matrix):
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    if request.method == 'POST':
        skill_id = request.POST.get('skill_id')
        try:
            actual_level = int(request.POST.get('actual_level', 0))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'actual_level must be a number'}, status=400)

        if skill_id:
            skill = get_object_or_404(Skill, id=skill_id)
            emp_skill, created = EmployeeSkill.objects.update_or_create(
                skill_matrix=skill_matrix,
                skill=skill,
                defaults={'actual_level': actual_level}
            )

            if emp_skill.self_rated_level is not None:
                if actual_level != emp_skill.self_rated_level:
                    emp_skill.rating_status = 'overridden'
                elif emp_skill.has_active_development_plan:
                    # Matches the self-rating, but an open development plan means the gap
                    # it was raised for isn't validated yet — leave it pending review.
                    emp_skill.rating_status = 'pending'
                else:
                    emp_skill.rating_status = 'approved'
                emp_skill.save(update_fields=['rating_status'])

            benchmark = SkillBenchmark.objects.filter(role_matrix=skill_matrix.role_matrix, skill=skill).first()
            required = benchmark.required_level if benchmark else 0
            gap = required - actual_level

            return JsonResponse({
                'success': True,
                'emp_skill_id': emp_skill.id,
                'actual_level': actual_level,
                'required_level': required,
                'gap': gap,
                'status': 'met' if gap <= 0 else ('warning' if gap <= 1 else 'critical'),
                'rating_status': emp_skill.rating_status,
            })
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


@login_required
def employee_self_rating_update(request, pk):
    """AJAX view for an employee to submit their own self-rating."""
    skill_matrix = get_object_or_404(SkillMatrix, pk=pk)
    if skill_matrix.user_id != request.user.id:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    if request.method == 'POST':
        skill_id = request.POST.get('skill_id')
        try:
            self_rated_level = int(request.POST.get('self_rated_level', 0))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'self_rated_level must be a number'}, status=400)

        if skill_id:
            skill = get_object_or_404(Skill, id=skill_id)
            emp_skill, created = EmployeeSkill.objects.update_or_create(
                skill_matrix=skill_matrix,
                skill=skill,
                defaults={'self_rated_level': self_rated_level, 'self_rated_on': date.today(), 'rating_status': 'pending'},
            )
            return JsonResponse({
                'success': True,
                'emp_skill_id': emp_skill.id,
                'self_rated_level': self_rated_level,
                'rating_status': emp_skill.rating_status,
            })

    return JsonResponse({'success': False, 'error': 'Invalid request'})


@login_required
def employee_skill_approve(request, pk, skill_id):
    """Accept the employee's self-rating as the official level, in one click."""
    skill_matrix = get_object_or_404(SkillMatrix, pk=pk)
    if not user_can_manage_employee(request.user, skill_matrix):
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    if request.method == 'POST':
        emp_skill = get_object_or_404(EmployeeSkill, skill_matrix=skill_matrix, skill_id=skill_id)
        if emp_skill.self_rated_level is not None:
            if emp_skill.has_active_development_plan:
                return JsonResponse({
                    'success': False,
                    'error': 'This skill has an active development plan. Mark it Completed before approving the self-rating.',
                }, status=409)
            emp_skill.actual_level = emp_skill.self_rated_level
            emp_skill.rating_status = 'approved'
            emp_skill.save()

        benchmark = SkillBenchmark.objects.filter(role_matrix=skill_matrix.role_matrix, skill_id=skill_id).first()
        required = benchmark.required_level if benchmark else 0
        gap = required - emp_skill.actual_level

        return JsonResponse({
            'success': True,
            'emp_skill_id': emp_skill.id,
            'actual_level': emp_skill.actual_level,
            'rating_status': emp_skill.rating_status,
            'required_level': required,
            'gap': gap,
            'status': 'met' if gap <= 0 else ('warning' if gap <= 1 else 'critical'),
        })

    return JsonResponse({'success': False, 'error': 'Invalid request'})


class SkillMatrixProfileUpdateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = SkillMatrix
    form_class = SkillMatrixForm
    template_name = 'gap_analysis/employee_profile.html'
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('skillgap_employee_list')
    success_message = "Employee updated successfully!"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit_mode'] = True
        return context


# --- DESIGNATION BENCHMARK MANAGEMENT ---
class RoleMatrixBenchmarkView(LoginRequiredMixin, TemplateView):
    template_name = 'gap_analysis/designation_benchmark.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        designation = get_object_or_404(RoleMatrix, pk=self.kwargs['pk'])
        benchmarks = SkillBenchmark.objects.filter(role_matrix=designation).select_related('skill')
        
        context['designation'] = designation
        context['benchmarks'] = benchmarks
        context['benchmark_count'] = benchmarks.count()
        return context


class RoleMatrixBenchmarkAddView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = SkillBenchmark
    form_class = RoleMatrixBenchmarkForm
    template_name = 'gap_analysis/add_form.html'
    success_message = "Skill benchmark added successfully!"

    def get_success_url(self):
        return reverse('skillgap_designation_benchmark', kwargs={'pk': self.kwargs['pk']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        designation = get_object_or_404(RoleMatrix, pk=self.kwargs['pk'])
        context['title'] = f'Add Skill to {designation.title}'
        context['designation'] = designation
        context['existing_skills'] = Skill.objects.all()
        return context

    def form_valid(self, form):
        designation = get_object_or_404(RoleMatrix, pk=self.kwargs['pk'])
        skill = form.cleaned_data.get('skill')
        if skill:
            form.instance.skill = skill
        form.instance.role_matrix = designation
        return super().form_valid(form)


class RoleMatrixBenchmarkDeleteView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, DeleteView):
    model = SkillBenchmark
    template_name = 'gap_analysis/benchmark_confirm_delete.html'
    success_message = "Benchmark removed successfully!"
    
    def get_success_url(self):
        return reverse('skillgap_designation_benchmark', kwargs={'pk': self.object.role_matrix.pk})


# --- Development Plans ---
class DevelopmentPlanCreateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = DevelopmentPlan
    form_class = DevelopmentPlanForm
    template_name = 'gap_analysis/add_form.html'
    success_message = "Development plan created successfully!"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        employee = get_object_or_404(SkillMatrix, pk=self.kwargs['pk'])
        skill_ids = set(employee.get_required_benchmarks().values_list('skill_id', flat=True))
        skill_ids |= set(employee.skills.values_list('skill_id', flat=True))
        form.fields['skill'].queryset = Skill.objects.filter(id__in=skill_ids) if skill_ids else Skill.objects.all()
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'New Development Plan'
        context['employee'] = get_object_or_404(SkillMatrix, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        employee = get_object_or_404(SkillMatrix, pk=self.kwargs['pk'])
        form.instance.skill_matrix = employee
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('skillgap_employee_profile', kwargs={'pk': self.kwargs['pk']})


class DevelopmentPlanUpdateView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = DevelopmentPlan
    form_class = DevelopmentPlanForm
    template_name = 'gap_analysis/add_form.html'
    success_message = "Development plan updated successfully!"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        employee = self.object.skill_matrix
        skill_ids = set(employee.get_required_benchmarks().values_list('skill_id', flat=True))
        skill_ids |= set(employee.skills.values_list('skill_id', flat=True))
        form.fields['skill'].queryset = Skill.objects.filter(id__in=skill_ids) if skill_ids else Skill.objects.all()
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Development Plan: {self.object.action}'
        context['employee'] = self.object.skill_matrix
        return context

    def get_success_url(self):
        return reverse('skillgap_employee_profile', kwargs={'pk': self.object.skill_matrix.pk})


class DevelopmentPlanDeleteView(LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, DeleteView):
    model = DevelopmentPlan
    template_name = 'gap_analysis/development_plan_confirm_delete.html'
    success_message = "Development plan deleted successfully!"

    def get_success_url(self):
        return reverse('skillgap_employee_profile', kwargs={'pk': self.object.skill_matrix.pk})


class DevelopmentPlanListView(LoginRequiredMixin, ListView):
    model = DevelopmentPlan
    template_name = 'gap_analysis/development_plan_list.html'
    context_object_name = 'plans'
    paginate_by = 15

    def get_queryset(self):
        queryset = DevelopmentPlan.objects.select_related('skill_matrix', 'skill')
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_status'] = self.request.GET.get('status')
        context['status_choices'] = DevelopmentPlan.STATUS_CHOICES
        return context


# --- Self vs. Manager Rating ---
class MySkillsView(LoginRequiredMixin, TemplateView):
    template_name = 'gap_analysis/my_skills.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = SkillMatrix.objects.filter(user=self.request.user).first()
        context['employee'] = employee

        if employee:
            skill_data = []
            for benchmark in employee.get_required_benchmarks():
                emp_skill = EmployeeSkill.objects.filter(skill_matrix=employee, skill=benchmark.skill).first()
                skill_data.append({
                    'skill_id': benchmark.skill.id,
                    'skill_name': benchmark.skill.name,
                    'skill_category': benchmark.skill.category,
                    'required_level': benchmark.required_level,
                    'actual_level': emp_skill.actual_level if emp_skill else 0,
                    'self_rated_level': emp_skill.self_rated_level if emp_skill else None,
                    'rating_status': emp_skill.rating_status if emp_skill else 'none',
                })
            context['skill_data'] = skill_data

        return context


class PendingReviewsListView(LoginRequiredMixin, ListView):
    model = EmployeeSkill
    template_name = 'gap_analysis/pending_reviews.html'
    context_object_name = 'pending_ratings'
    paginate_by = 20

    def get_queryset(self):
        queryset = EmployeeSkill.objects.filter(rating_status='pending').select_related('skill_matrix', 'skill')
        if not self.request.user.is_staff:
            manager_record = SkillMatrix.objects.filter(user=self.request.user).first()
            queryset = queryset.filter(skill_matrix__manager=manager_record) if manager_record else queryset.none()
        return queryset


# --- Employee Skill Search ---
class EmployeeSkillSearchView(LoginRequiredMixin, TemplateView):
    template_name = 'gap_analysis/employee_skill_search.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['skills'] = Skill.objects.all().order_by('name')

        selected_skill = None
        results = []

        skill_id = self.request.GET.get('skill')
        if skill_id:
            selected_skill = Skill.objects.filter(id=skill_id).first()

        if selected_skill:
            matching_skills = EmployeeSkill.objects.filter(
                skill=selected_skill
            ).select_related('skill_matrix__role_matrix', 'skill_matrix__employee', 'skill').order_by('-actual_level', 'skill_matrix__employee__name')

            results = [
                {
                    'employee': es.skill_matrix,
                    'skill': es.skill.name,
                    'level': es.actual_level,
                }
                for es in matching_skills
            ]

        context['selected_skill'] = selected_skill
        context['results'] = results
        return context


class HelpView(LoginRequiredMixin, TemplateView):
    template_name = 'gap_analysis/help.html'