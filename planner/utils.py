# planner/utils.py

from datetime import date, timedelta

def calculate_end_date(start_date, duration_days, holidays):
    """
    Calculates the end date for a project, skipping weekends and holidays.
    
    Args:
        start_date (date): The starting date of the project.
        duration_days (int): The number of working days the project will take.
        holidays (list): A list of date objects representing company holidays.
    
    Returns:
        date: The calculated end date.
    """
    if duration_days <= 0:
        return start_date

    work_days_counted = 0
    current_date = start_date
    
    while work_days_counted < duration_days:
        # Monday is 0 and Sunday is 6
        if current_date.weekday() < 5 and current_date not in holidays:
            work_days_counted += 1
        
        # Move to the next day unless we've found the end date
        if work_days_counted < duration_days:
            current_date += timedelta(days=1)
            
    return current_date

def count_working_days(start_date, end_date, holidays):
    """Counts the number of working days between two dates, inclusive."""
    if start_date > end_date:
        return 0
    
    working_days = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5 and current_date not in holidays:
            working_days += 1
        current_date += timedelta(days=1)
    return working_days

def calculate_effort_from_value(value, brackets):
    """
    Calculates the estimated effort in days based on a project's value,
    using linear interpolation between configured brackets.
    """
    if not brackets or len(brackets) < 1:
        return 0

    # Sort brackets by project_value to be safe
    sorted_brackets = sorted(brackets, key=lambda b: b.project_value)
    
    # Case 1: Value is below the lowest bracket
    if value <= sorted_brackets[0].project_value:
        first_bracket = sorted_brackets[0]
        # Scale proportionally from (0, 0) to the first bracket
        if first_bracket.project_value == 0: return first_bracket.effort_days
        return (value / first_bracket.project_value) * first_bracket.effort_days

    # Case 2: Value is above the highest bracket
    if value >= sorted_brackets[-1].project_value:
        # Extrapolate using the top two brackets
        if len(sorted_brackets) < 2:
            return sorted_brackets[-1].effort_days
            
        last_bracket = sorted_brackets[-1]
        second_last_bracket = sorted_brackets[-2]
        
        x1, y1 = second_last_bracket.project_value, second_last_bracket.effort_days
        x2, y2 = last_bracket.project_value, last_bracket.effort_days

        if (x2 - x1) == 0: return y2
        
        # Extrapolation formula
        effort = y1 + ((value - x1) * (y2 - y1)) / (x2 - x1)
        return effort

    # Case 3: Value is between two brackets (Interpolation)
    lower_bracket = None
    upper_bracket = None
    for bracket in sorted_brackets:
        if bracket.project_value <= value:
            lower_bracket = bracket
        if bracket.project_value > value:
            upper_bracket = bracket
            break

    if lower_bracket and upper_bracket:
        x1, y1 = lower_bracket.project_value, lower_bracket.effort_days
        x2, y2 = upper_bracket.project_value, upper_bracket.effort_days
        
        if (x2 - x1) == 0: return y2
        
        # Interpolation formula
        effort = y1 + ((value - x1) * (y2 - y1)) / (x2 - x1)
        return effort
    
    # Fallback if something goes wrong
    return 0