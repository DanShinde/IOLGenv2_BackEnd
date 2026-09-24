from django.utils import timezone
import datetime

# Stages that never count toward any OTIF figure. Dispatch is only used by the Emulation
# Timing Analysis; Handover has its own dedicated figure (get_final_project_otif).
OTIF_EXCLUDED_STAGES = ('Dispatch', 'Handover')

def get_completion_percentage(stages):
    stages = [s for s in stages if s.status != "Not Applicable"]
    total = len(stages)
    if total == 0: return 0
    total_progress = sum(s.completion_percentage for s in stages)
    return round(total_progress / total)

def get_otif_percentage(stages):
    completed = [s for s in stages if s.status == 'Completed' and s.name not in OTIF_EXCLUDED_STAGES]
    if not completed:
        return None
    on_time = [s for s in completed if s.actual_date and s.planned_date and s.actual_date <= s.planned_date]
    return round((len(on_time) / len(completed)) * 100, 1)

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

def get_next_milestone(stages):
    """
    Finds the first stage in a given list that is not 'Completed' or 'Not Applicable'.
    Assumes the list of stages is already sorted by ID.
    """
    for stage in stages:
        if stage.status not in ['Completed', 'Not Applicable']:
            return stage
    return None