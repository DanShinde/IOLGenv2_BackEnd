"""Shared data-building for the team skill gap report (Excel + PDF).

Both export formats render this exact same structure so they can never disagree with
each other. The weighted-gap math mirrors gap_weight()/SkillMatrix.get_overall_gap_score()
in models.py rather than re-deriving it.
"""
from collections import defaultdict

from .models import SkillBenchmark, EmployeeSkill, gap_weight


def build_team_report_data(employees):
    """employees: a SkillMatrix queryset or list, e.g. SkillMatrix.objects.all()."""
    employees = list(employees.select_related('role_matrix', 'employee').order_by('employee__name'))
    employee_ids = [e.id for e in employees]
    role_ids = {e.role_matrix_id for e in employees if e.role_matrix_id}

    benchmarks = list(
        SkillBenchmark.objects.filter(role_matrix_id__in=role_ids).select_related('skill', 'role_matrix')
    )
    benchmark_map = {(b.role_matrix_id, b.skill_id): b for b in benchmarks}

    skill_by_id = {b.skill_id: b.skill for b in benchmarks}
    skills = sorted(skill_by_id.values(), key=lambda s: s.name)

    actual_levels = defaultdict(dict)  # emp_id -> {skill_id: actual_level}
    for es in EmployeeSkill.objects.filter(skill_matrix_id__in=employee_ids, skill__isnull=False):
        actual_levels[es.skill_matrix_id][es.skill_id] = es.actual_level

    matrix = {}
    total_weighted_gap = 0
    total_weight = 0
    skills_met_count = 0
    skills_compared_count = 0

    emp_gap_totals = defaultdict(lambda: {'weighted_gap': 0, 'weight': 0})
    skill_gap_totals = defaultdict(lambda: {'total_gap': 0, 'count': 0})
    role_gap_totals = defaultdict(lambda: {'weighted_gap': 0, 'weight': 0, 'employee_ids': set()})

    for emp in employees:
        for skill in skills:
            bm = benchmark_map.get((emp.role_matrix_id, skill.id))
            if bm is None:
                matrix[(emp.id, skill.id)] = {'applicable': False}
                continue

            actual = actual_levels[emp.id].get(skill.id, 0)
            gap = bm.required_level - actual
            weight = gap_weight(bm.is_mandatory)
            status = 'met' if gap <= 0 else ('warning' if gap <= 1 else 'critical')

            matrix[(emp.id, skill.id)] = {
                'applicable': True,
                'required': bm.required_level,
                'actual': actual,
                'gap': gap,
                'status': status,
                'is_mandatory': bm.is_mandatory,
            }

            total_weighted_gap += gap * weight
            total_weight += weight
            skills_compared_count += 1
            if gap <= 0:
                skills_met_count += 1

            emp_gap_totals[emp.id]['weighted_gap'] += gap * weight
            emp_gap_totals[emp.id]['weight'] += weight

            if gap > 0:
                skill_gap_totals[skill.id]['total_gap'] += gap
                skill_gap_totals[skill.id]['count'] += 1

            if emp.role_matrix_id:
                role_gap_totals[emp.role_matrix_id]['weighted_gap'] += gap * weight
                role_gap_totals[emp.role_matrix_id]['weight'] += weight
                role_gap_totals[emp.role_matrix_id]['employee_ids'].add(emp.id)

    summary = {
        'total_employees': len(employees),
        'total_skills': len(skills),
        'avg_gap_score': round(total_weighted_gap / total_weight, 2) if total_weight else 0,
        'skills_met_pct': round((skills_met_count / skills_compared_count) * 100) if skills_compared_count else 0,
    }

    gap_by_employee = []
    for emp in employees:
        totals = emp_gap_totals.get(emp.id)
        if not totals or totals['weight'] == 0:
            continue
        gap_by_employee.append({
            'name': emp.name,
            'role': emp.role_matrix.title if emp.role_matrix else '-',
            'avg_gap': round(totals['weighted_gap'] / totals['weight'], 2),
        })
    gap_by_employee.sort(key=lambda x: x['avg_gap'], reverse=True)

    gap_by_skill = []
    for skill in skills:
        totals = skill_gap_totals.get(skill.id)
        if not totals:
            continue
        gap_by_skill.append({
            'name': skill.name,
            'avg_gap': round(totals['total_gap'] / totals['count'], 2),
            'affected_count': totals['count'],
        })
    gap_by_skill.sort(key=lambda x: x['avg_gap'], reverse=True)
    gap_by_skill = gap_by_skill[:10]

    role_title_by_id = {emp.role_matrix_id: emp.role_matrix.title for emp in employees if emp.role_matrix_id}
    gap_by_role = []
    for role_id, totals in role_gap_totals.items():
        if totals['weight'] == 0:
            continue
        gap_by_role.append({
            'role': role_title_by_id.get(role_id, '-'),
            'avg_gap': round(totals['weighted_gap'] / totals['weight'], 2),
            'employee_count': len(totals['employee_ids']),
        })
    gap_by_role.sort(key=lambda x: x['avg_gap'], reverse=True)

    return {
        'employees': employees,
        'skills': skills,
        'matrix': matrix,
        'summary': summary,
        'gap_by_employee': gap_by_employee,
        'gap_by_skill': gap_by_skill,
        'gap_by_role': gap_by_role,
    }
