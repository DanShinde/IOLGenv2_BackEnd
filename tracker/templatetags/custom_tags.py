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
    try:
        return lst[index + 1]
    except:
        return None

from django import template

register = template.Library()

@register.filter
def abs_value(value):
    try:
        return abs(int(value))
    except:
        return value

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)