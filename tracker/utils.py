def get_completion_percentage(stages):
    stages = [s for s in stages if s.status != "Not Applicable"]
    total = len(stages)
    completed = sum(1 for s in stages if s.status == "Completed")
    return round((completed / total) * 100) if total > 0 else 0

def get_otif_percentage(stages):
    completed = [s for s in stages if s.status == 'Completed']
    if not completed:
        return None
    on_time = [s for s in completed if s.actual_date and s.planned_date and s.actual_date <= s.planned_date]
    return round((len(on_time) / len(completed)) * 100, 1)

def get_overall_status(stages):
    if any(s.status == 'Hold' for s in stages):
        return 'Hold'
    if any(s.name == 'Handover' and s.status == 'Completed' for s in stages):
        return 'Completed'
    if any(s.status not in ['Not started', 'Hold'] for s in stages):
        return 'In Progress'
    if all(s.status == 'Not started' for s in stages):
        return 'Not started'
    return 'Not started'

def get_schedule_status(stages):
    completed = [s for s in stages if s.status == 'Completed']
    if not completed:
        return None
    last = completed[-1]
    if last.actual_date and last.planned_date:
        return (last.actual_date - last.planned_date).days
    return None

def get_next_milestone(stages):
    completed = [s for s in stages if s.status == 'Completed']
    if not stages:
        return None
    if not completed:
        return stages[0]
    if completed[-1] in stages:
        idx = stages.index(completed[-1])
        return stages[idx + 1] if idx + 1 < len(stages) else None
    return None
