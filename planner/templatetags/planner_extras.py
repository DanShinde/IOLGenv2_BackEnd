# planner/templatetags/planner_extras.py

from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Gets an item from a dictionary."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter(name='get_attribute')
def get_attribute(obj, attr_name):
    """Gets an attribute from an object."""
    return getattr(obj, attr_name, None)