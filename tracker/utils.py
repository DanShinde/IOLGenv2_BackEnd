from django.db.models import F, Q
from django.utils import timezone
import datetime

# ---------------------------------------------------------------------------------------
# OTIF -- the one definition used everywhere (project, phase, dashboard, reports, exports)
#
#   OTIF % = due stages completed on or before their planned date / due stages
#
# A stage is "due" when its planned date is inside the period and on or before today.
# Every due stage that isn't completed on time is a miss: completed late, or still open
# past its planned date. Stages are bucketed into periods by PLANNED date.
# Never counted: Not Applicable, Hold (holds are customer-side), Dispatch and Handover
# (Handover has its own Early / On Time / Late figure), and bad data -- planned dates more
# than OTIF_MAX_DAY_DELTA days old (typo years like 0020) or Completed stages with no
# usable actual date.
# ---------------------------------------------------------------------------------------

# Stages that never count toward any OTIF figure. Dispatch is only used by the Emulation
# Timing Analysis; Handover has its own dedicated figure (get_final_project_otif).
OTIF_EXCLUDED_STAGES = ('Dispatch', 'Handover')
OTIF_EXCLUDED_STATUSES = ('Not Applicable', 'Hold')
OTIF_MAX_DAY_DELTA = 3650  # ~10 years; same bound as the Reports' MAX_PLAUSIBLE_DAY_DELTA


def _otif_window(start, end, today):
    today = today or timezone.localdate()
    floor = today - datetime.timedelta(days=OTIF_MAX_DAY_DELTA)
    lo = max(start, floor) if start else floor
    hi = min(end, today) if end else today
    return lo, hi, floor


def otif_due_q(start=None, end=None, today=None):
    """Q selecting the stages that count toward OTIF for [start, end] (either may be None)."""
    lo, hi, floor = _otif_window(start, end, today)
    return (
        Q(planned_date__isnull=False, planned_date__gte=lo, planned_date__lte=hi)
        & ~Q(status__in=OTIF_EXCLUDED_STATUSES)
        & ~Q(name__in=OTIF_EXCLUDED_STAGES)
        & ~Q(status='Completed', actual_date__isnull=True)
        & ~Q(status='Completed', actual_date__lt=floor)
    )


# A due stage is on time when it was completed on or before its planned date.
OTIF_ON_TIME_Q = Q(status='Completed', actual_date__lte=F('planned_date'))


def otif_pct(on_time, due):
    return round(on_time / due * 100, 1) if due else None


def otif_counts_qs(stages_qs, start=None, end=None, today=None):
    """(on_time, due) for a Stage queryset."""
    due_qs = stages_qs.filter(otif_due_q(start, end, today))
    return due_qs.filter(OTIF_ON_TIME_Q).count(), due_qs.count()


def is_otif_due(stage, start=None, end=None, today=None):
    """Python twin of otif_due_q for stages already in memory."""
    lo, hi, floor = _otif_window(start, end, today)
    if not stage.planned_date or not (lo <= stage.planned_date <= hi):
        return False
    if stage.status in OTIF_EXCLUDED_STATUSES or stage.name in OTIF_EXCLUDED_STAGES:
        return False
    if stage.status == 'Completed' and (not stage.actual_date or stage.actual_date < floor):
        return False
    return True


def is_otif_on_time(stage):
    return stage.status == 'Completed' and stage.actual_date <= stage.planned_date


def get_otif_counts(stages, start=None, end=None, today=None):
    """(on_time, due) for stages already in memory."""
    due = [s for s in stages if is_otif_due(s, start, end, today)]
    return sum(1 for s in due if is_otif_on_time(s)), len(due)


def get_otif_percentage(stages, start=None, end=None, today=None):
    return otif_pct(*get_otif_counts(stages, start, end, today))


def get_completion_percentage(stages):
    stages = [s for s in stages if s.status != "Not Applicable"]
    total = len(stages)
    if total == 0: return 0
    total_progress = sum(s.completion_percentage for s in stages)
    return round(total_progress / total)

def get_final_project_otif(stages):
    """
    Calculates the final project OTIF based only on the 'Handover' stage.
    Returns:
    - 101 if completed BEFORE the planned date.
    - 100 if completed ON the planned date.
    - 0 if completed AFTER the planned date.
    - None if not yet completed or dates are missing.
    """
    try:
        handover_stage = next(s for s in stages if s.name == "Handover")
        
        if handover_stage.status == 'Completed':
            if handover_stage.actual_date and handover_stage.planned_date:
                if handover_stage.actual_date < handover_stage.planned_date:
                    return 101  # Before Time
                elif handover_stage.actual_date == handover_stage.planned_date:
                    return 100  # On Time
                else:
                    return 0    # Delayed
    except StopIteration:
        return None
        
    return None

def get_overall_status(stages):
    if any(s.status == 'Hold' for s in stages):
        return 'Hold'
    
    handover = next((s for s in stages if s.name == 'Handover'), None)
    if handover and handover.status == 'Completed':
        return 'Completed'
        
    if any(s.status not in ['Not started', 'Hold', 'Not Applicable'] for s in stages):
        return 'In Progress'
    return 'Not started'

def get_timeline_progress(stages):
    """How far along the roadmap line to fill: position of the last Completed stage among
    the applicable ones (0-100)."""
    applicable = [s for s in stages if s.status != 'Not Applicable']
    last_completed = -1
    for i, s in enumerate(applicable):
        if s.status == 'Completed':
            last_completed = i
    segments = len(applicable) - 1
    if last_completed >= 0 and segments > 0:
        return round((last_completed / segments) * 100)
    return 0

def sort_stages_by_phase(stages, order_map):
    """Phase order first (project-level Handover, which has no phase, last), then the
    canonical stage-list order within each phase. Stages need `phase` loaded."""
    return sorted(
        stages,
        key=lambda s: (s.phase.number if s.phase_id else 10**6, order_map.get(s.name, 99)),
    )

def get_phase_summary(phase, stages):
    """Roll-up for one phase's stages. Dates are derived here, never stored."""
    applicable = [s for s in stages if s.status != 'Not Applicable']
    if not applicable:
        status = 'Not Applicable'
    elif any(s.status == 'Hold' for s in applicable):
        status = 'Hold'
    elif all(s.status == 'Completed' for s in applicable):
        status = 'Completed'
    elif any(s.status != 'Not started' for s in applicable):
        status = 'In Progress'
    else:
        status = 'Not started'

    planned = [s.planned_date for s in applicable if s.planned_date]
    actual = [s.actual_date for s in applicable if s.actual_date]
    return {
        'phase': phase,
        'status': status,
        'completion': get_completion_percentage(stages),
        'planned_finish': max(planned) if planned else None,
        'actual_finish': max(actual) if (actual and status == 'Completed') else None,
        'otif': get_otif_percentage(stages),
        'stage_count': len(applicable),
    }

def get_schedule_status(stages):
    completed = [s for s in stages if s.status == 'Completed' and s.actual_date and s.planned_date]
    if not completed:
        return None
    # Sort by ID to ensure we get the last chronological stage
    last = sorted(completed, key=lambda s: s.id)[-1]
    return (last.actual_date - last.planned_date).days

def get_live_schedule_status(stages, today=None, max_delta=3650):
    """Current schedule position of one stream (used only by the Project Detail summary;
    Reports keep get_schedule_status). `stages` must be in workflow order.

    1. The earliest open stage (anything not Completed) past its planned date sets the
       delay: today - planned. This catches slips before the stage is marked Completed.
    2. Otherwise the latest completed stage, in workflow order, gives actual - planned.
    3. Otherwise On Time if any planned date exists, else None (not enough data).

    Returns {'days', 'stage', 'overdue'} or None. Days are calendar days; +ve = delayed.
    Gaps beyond max_delta days (typo dates like year 0020) are skipped as bad data, the
    same bound the Reports use (MAX_PLAUSIBLE_DAY_DELTA).
    """
    today = today or timezone.localdate()
    applicable = [s for s in stages if s.status != 'Not Applicable']

    for s in applicable:
        if s.status != 'Completed' and s.planned_date and 0 < (today - s.planned_date).days <= max_delta:
            return {'days': (today - s.planned_date).days, 'stage': s, 'overdue': True}

    completed = [s for s in applicable if s.status == 'Completed' and s.planned_date and s.actual_date
                 and abs((s.actual_date - s.planned_date).days) <= max_delta]
    if completed:
        last = completed[-1]
        return {'days': (last.actual_date - last.planned_date).days, 'stage': last, 'overdue': False}

    if any(s.planned_date for s in applicable):
        return {'days': 0, 'stage': None, 'overdue': False}
    return None

def get_next_milestone(stages):
    """
    Finds the first stage in a given list that is not 'Completed' or 'Not Applicable'.
    Assumes the list of stages is already sorted by ID.
    """
    for stage in stages:
        if stage.status not in ['Completed', 'Not Applicable']:
            return stage
    return None