from django import template

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