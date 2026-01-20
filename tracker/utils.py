from django.utils import timezone
import datetime

def get_completion_percentage(stages):
    stages = [s for s in stages if s.status != "Not Applicable"]
    total = len(stages)
    if total == 0: return 0
    total_progress = sum(s.completion_percentage for s in stages)
    return round(total_progress / total)

def get_otif_percentage(stages):
    completed = [s for s in stages if s.status == 'Completed']
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