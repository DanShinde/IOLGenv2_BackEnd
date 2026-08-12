"""Pure calculation of a project's effort estimate. No HTTP here -- this is the single
source of truth consumed by the builder page, the report page, and both exporters, so
the numbers a user sees on screen always match what's saved to PDF/Excel.

Nothing is snapshotted: every call recomputes from the *current* matrix/complexity
config, so a duplicated project always reflects whatever the matrix says today.
"""
from decimal import Decimal

from .models import Activity, ModuleActivityTime


def build_project_estimate(project):
    modules = list(
        project.modules.select_related('segment', 'module_type', 'complexity_override').order_by('order', 'id')
    )
    activities = list(Activity.objects.order_by('display_order', 'name'))

    matrix = {
        (t.segment_id, t.module_type_id, t.activity_id): t.minutes
        for t in ModuleActivityTime.objects.all()
    }

    activity_totals = {a.id: Decimal('0') for a in activities}
    rows = []
    grand_total = Decimal('0')
    warnings = []
    warned_combos = set()

    for pm in modules:
        complexity = pm.effective_complexity
        factor = complexity.multiplier if complexity else Decimal('1')
        mt = pm.module_type
        segment = pm.segment

        has_any_time = any((segment.id, mt.id, a.id) in matrix for a in activities)
        if not has_any_time and (segment.id, mt.id) not in warned_combos:
            warnings.append(f"'{mt.name}' in '{segment.name}' has no configured activity times yet -- its estimate will be 0.")
            warned_combos.add((segment.id, mt.id))

        row_activities = []
        row_total = Decimal('0')
        for a in activities:
            base_minutes = matrix.get((segment.id, mt.id, a.id), Decimal('0'))
            minutes = base_minutes * pm.count * factor
            row_activities.append({
                'activity': a,
                'base_minutes': base_minutes,
                'minutes': minutes,
            })
            activity_totals[a.id] += minutes
            row_total += minutes

        rows.append({
            'module': pm,
            'segment': segment,
            'module_type': mt,
            'count': pm.count,
            'complexity': complexity,
            'activities': row_activities,
            'row_total_minutes': row_total,
        })
        grand_total += row_total

    per_day = project.minutes_per_working_day or 480

    return {
        'project': project,
        'rows': rows,
        'activities': activities,
        'activity_totals': [
            {'activity': a, 'total_minutes': activity_totals[a.id]} for a in activities
        ],
        'grand_total_minutes': grand_total,
        'grand_total_hours': grand_total / Decimal('60'),
        'grand_total_days': grand_total / Decimal(per_day),
        'minutes_per_day': per_day,
        'warnings': warnings,
    }
