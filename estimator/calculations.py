"""Pure calculation of a project's effort estimate. No HTTP here -- this is the single
source of truth consumed by the builder page, the report page, and both exporters, so
the numbers a user sees on screen always match what's saved to PDF/Excel.

Nothing is snapshotted: every call recomputes from the *current* matrix/complexity
config, so a duplicated project always reflects whatever the matrix says today.
"""
from decimal import Decimal

from .models import Activity, ActivityCategory, ModuleActivityTime

UNASSIGNED_ZONE = 'Unassigned'


def build_project_estimate(project):
    modules = list(
        project.modules.select_related('segment', 'module_type', 'complexity_override').order_by('order', 'id')
    )
    activities = list(Activity.objects.order_by('category', 'display_order', 'name'))
    per_day = project.minutes_per_working_day or 480

    # effective_minutes() resolves 'day'-unit cells using this project's own
    # minutes_per_working_day, so the same matrix cell can be worth a different
    # number of minutes on a project with a different working-day length.
    matrix = {
        (t.segment_id, t.module_type_id, t.activity_id): t.effective_minutes(per_day)
        for t in ModuleActivityTime.objects.all()
    }

    rows = []
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

        # modified_count (set by hand on Module Summary) overrides count for every
        # calculation when present -- see ProjectModule.effective_count.
        effective_count = pm.effective_count

        row_activities = []
        row_total = Decimal('0')
        for a in activities:
            base_minutes = matrix.get((segment.id, mt.id, a.id), Decimal('0'))
            minutes = base_minutes * effective_count * factor
            row_activities.append({
                'activity': a,
                'base_minutes': base_minutes,
                'complexity_multiplier': factor,
                'minutes': minutes,
                'days': minutes / Decimal(per_day),
            })
            row_total += minutes

        rows.append({
            'module': pm,
            'segment': segment,
            'module_type': mt,
            'count': pm.count,
            'modified_count': pm.modified_count,
            'effective_count': effective_count,
            'zone': pm.zone or UNASSIGNED_ZONE,
            'complexity': complexity,
            'activities': row_activities,
            'row_total_minutes': row_total,
            'row_total_days': row_total / Decimal(per_day),
        })

    summary = _summarize(rows, activities, per_day)

    # Every module row carries a zone (imported, manually typed, or the UNASSIGNED_ZONE
    # fallback), so re-slicing the same rows/totals by zone -- like category_groups
    # already does by activity category -- gives each zone its own self-contained
    # estimate without recomputing anything against the matrix a second time.
    rows_by_zone = {}
    for r in rows:
        rows_by_zone.setdefault(r['zone'], []).append(r)

    zone_groups = [
        {'zone': zone_name, 'rows': zone_rows, **_summarize(zone_rows, activities, per_day)}
        for zone_name, zone_rows in sorted(
            rows_by_zone.items(), key=lambda item: (item[0] == UNASSIGNED_ZONE, item[0].lower())
        )
    ]

    return {
        'project': project,
        'rows': rows,
        'activities': activities,
        'zone_groups': zone_groups,
        'minutes_per_day': per_day,
        'warnings': warnings,
        **summary,
    }


def _summarize(rows, activities, per_day):
    """Activity totals + category-grouped breakdown + grand totals for a given set of
    estimate rows. Used for the whole project and, identically, for each zone's own
    slice of rows -- so a zone's numbers are computed exactly the same way the
    project's are, just over fewer rows."""

    activity_totals = {a.id: Decimal('0') for a in activities}
    # Per activity, every module row that actually contributes minutes to it, with enough
    # detail (rate, count, complexity) to show the full "rate x count x complexity"
    # arithmetic on demand -- not just the resulting number.
    activity_contributions = {a.id: [] for a in activities}
    grand_total = Decimal('0')

    for r in rows:
        for ad in r['activities']:
            activity_totals[ad['activity'].id] += ad['minutes']
            if ad['minutes'] > 0:
                activity_contributions[ad['activity'].id].append({
                    'label': f"{r['module_type'].name} / {r['segment'].name}",
                    'base_minutes': ad['base_minutes'],
                    'count': r['effective_count'],
                    'complexity_multiplier': ad['complexity_multiplier'],
                    'minutes': ad['minutes'],
                })
        grand_total += r['row_total_minutes']

    activity_totals_list = [
        {
            'activity': a,
            'total_minutes': activity_totals[a.id],
            'total_days': activity_totals[a.id] / Decimal(per_day),
            'contributions': activity_contributions[a.id],
        }
        for a in activities
    ]

    # Every activity belongs to exactly one of the two fixed categories, so the same
    # rows/totals above can be re-sliced per category for category-grouped reporting
    # without recomputing anything.
    category_groups = []
    for cat_value, cat_label in ActivityCategory.choices:
        cat_activities = [a for a in activities if a.category == cat_value]
        if not cat_activities:
            continue
        cat_activity_ids = {a.id for a in cat_activities}

        cat_rows = []
        cat_total = Decimal('0')
        for r in rows:
            cat_row_activities = [ad for ad in r['activities'] if ad['activity'].id in cat_activity_ids]
            cat_row_total = sum((ad['minutes'] for ad in cat_row_activities), Decimal('0'))
            cat_rows.append({
                **r,
                'activities': cat_row_activities,
                'row_total_minutes': cat_row_total,
                'row_total_days': cat_row_total / Decimal(per_day),
            })
            cat_total += cat_row_total

        category_groups.append({
            'category': cat_value,
            'label': cat_label,
            'activities': cat_activities,
            'activity_totals': [at for at in activity_totals_list if at['activity'].id in cat_activity_ids],
            'rows': cat_rows,
            'total_minutes': cat_total,
            'total_hours': cat_total / Decimal('60'),
            'total_days': cat_total / Decimal(per_day),
        })

    return {
        'activity_totals': activity_totals_list,
        'category_groups': category_groups,
        'grand_total_minutes': grand_total,
        'grand_total_hours': grand_total / Decimal('60'),
        'grand_total_days': grand_total / Decimal(per_day),
    }
