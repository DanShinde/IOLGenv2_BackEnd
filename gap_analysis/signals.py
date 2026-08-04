from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from employees.models import Employee


@receiver(post_save, sender=Employee)
def sync_skill_matrix_with_employee(sender, instance, created, **kwargs):
    """Keep Skill Gap Analyzer's roster and active/inactive status in sync with the shared
    Employee list used by Planner/Tracker/Workforce -- whichever side an employee is
    activated/deactivated from, the other side should reflect it without manual upkeep.

    All writes to the OTHER model use .update() (a bulk queryset op) rather than
    instance.save(), specifically because .update() does not fire post_save -- that's what
    keeps this and sync_employee_active_from_skill_matrix() below from ping-ponging into an
    infinite loop of signals re-triggering each other.
    """
    if instance.name.startswith('Unassigned'):
        return

    from .models import SkillMatrix, find_matching_user

    sm = None if created else SkillMatrix.objects.filter(employee=instance).first()

    if sm is None:
        # Not in Skill Gap Analyzer's roster yet -- either a brand-new employee, or one that
        # was inactive since creation (so the roster never picked it up) and has now been
        # activated. Either way, bring it in the same way.
        if instance.is_active:
            SkillMatrix.objects.get_or_create(
                employee=instance,
                defaults={'user': find_matching_user(instance.name)},
            )
        return

    if not instance.is_active and sm.status != 'inactive':
        SkillMatrix.objects.filter(pk=sm.pk).update(status='inactive')
    elif instance.is_active and sm.status == 'inactive':
        # Reactivating just clears the "inactive" state -- if status is 'on_leave' (a more
        # specific, deliberately-set state), leave it as is rather than overwriting it.
        SkillMatrix.objects.filter(pk=sm.pk).update(status='active')


@receiver(post_save, sender=User)
def link_skill_matrix_user_on_user_change(sender, instance, **kwargs):
    """The reverse direction: if a login account is created (or its name is filled in/fixed)
    for someone whose SkillMatrix entry already exists but has no linked login yet, link it
    now rather than waiting for someone to notice and do it by hand. Never touches a
    SkillMatrix that already has a user -- an existing link may have been a deliberate manual
    fix for a spelling mismatch, and this must not clobber it.
    """
    if not instance.first_name or not instance.last_name:
        return

    from .models import SkillMatrix

    already_linked_elsewhere = SkillMatrix.objects.filter(user=instance).exists()
    if already_linked_elsewhere:
        return

    first = instance.first_name.strip().lower()
    last = instance.last_name.strip().lower()
    candidates = []
    for sm in SkillMatrix.objects.filter(user__isnull=True).select_related('employee'):
        parts = sm.employee.name.split()
        if len(parts) < 2:
            continue
        if parts[0].strip().lower() == first and parts[-1].strip().lower() == last:
            candidates.append(sm)

    if len(candidates) == 1:
        candidates[0].user = instance
        candidates[0].save(update_fields=['user'])


@receiver(post_save, sender='gap_analysis.SkillMatrix')
def sync_employee_active_from_skill_matrix(sender, instance, created, **kwargs):
    """The reverse direction of sync_skill_matrix_with_employee() above: if status is changed
    from the Skill Gap Analyzer side (e.g. staff marks someone Inactive there), the shared
    Employee record's is_active flag follows -- 'on_leave' counts as still active/employed,
    only 'inactive' does not."""
    if created:
        return

    # Checked and written in one queryset chain against employee_id, rather than via
    # instance.employee -- a cached FK access could go stale across multiple saves of the
    # same in-memory instance within one process, which would silently skip a needed update.
    should_be_active = instance.status != 'inactive'
    (
        Employee.objects
        .filter(pk=instance.employee_id)
        .exclude(is_active=should_be_active)
        .update(is_active=should_be_active)
    )
