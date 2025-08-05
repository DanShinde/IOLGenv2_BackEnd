from django import template
from django.utils import timezone
import datetime

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Allows you to access a dictionary value using a variable key in templates.
    Usage: {{ mydict|get_item:mykey }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def get_next(lst, index):
    """Gets the next item in a list."""
    try:
        return lst[index + 1]
    except IndexError:
        return None


@register.filter(name='abs')
def absolute_value(value):
    """Returns the absolute value of a number."""
    try:
        return abs(int(value))
    except (ValueError, TypeError):
        return value
    
@register.filter
def days_until(value):
    """
    Calculates the difference between a date and today and returns a
    human-readable string like 'Due today', '5 days overdue', etc.
    """
    if not isinstance(value, datetime.date):
        return ""  # Return empty string if value is not a date
    
    today = timezone.now().date()
    delta = value - today

    if delta.days == 0:
        return "Due today"
    elif delta.days == 1:
        return "Due in 1 day"
    elif delta.days > 1:
        return f"Due in {delta.days} days"
    elif delta.days == -1:
        return "1 day overdue"
    else:
        return f"{abs(delta.days)} days overdue"