from django import template

from inventory.people import person_name

register = template.Library()


@register.filter
def person(user):
    """{{ some_user|person }} - the person's employee name, as the other apps show it."""
    return person_name(user)
