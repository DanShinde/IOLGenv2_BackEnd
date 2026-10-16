"""
How inventory names a person.

Planner, Skill Gap and the other apps name people by employees.Employee.name
("Darshan Dharmendrasingh Pardeshi"). Inventory works with auth.User logins, which are
linked to an Employee through gap_analysis.SkillMatrix.user, and a login's own first/last
name is often shorter ("Darshan Pardeshi"). So every place inventory shows a person goes
through person_name(): the linked employee's name when there is one, otherwise the
login's full name, otherwise its username.

Kept free of model imports so models.py, forms.py and templates can all use it.
"""


def _clean(text):
    return ' '.join((text or '').split())  # also folds double spaces ("Darshan  Pardeshi")


def person_name(user):
    if user is None:
        return ''
    try:
        employee = user.skillmatrix.employee
    except Exception:  # no linked SkillMatrix / employee
        employee = None
    if employee is not None and _clean(employee.name):
        return _clean(employee.name)
    return _clean(user.get_full_name()) or user.username
