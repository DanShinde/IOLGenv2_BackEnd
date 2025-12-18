# employees/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from tracker.models import Pace
from .models import Employee
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Pace)
def sync_pace_to_employee(sender, instance, created, **kwargs):
    """
    Auto-create or update Employee when tracker Pace is created/updated.
    This makes Employee the unified model for all personnel across apps.
    """
    try:
        if created:
            # Check if an employee with the same name exists but isn't linked
            try:
                employee = Employee.objects.get(name=instance.name, tracker_pace__isnull=True)
                # Link existing employee to this pace
                employee.tracker_pace = instance
                if employee.designation != 'TEAM_LEAD':
                    logger.warning(f"Employee '{employee.name}' was {employee.designation}, changing to TEAM_LEAD to match Pace")
                    employee.designation = 'TEAM_LEAD'
                employee.save()
                logger.info(f"Linked existing employee '{employee.name}' to Pace '{instance.name}'")
            except Employee.DoesNotExist:
                # Auto-create new employee from Pace
                employee = Employee.objects.create(
                    name=instance.name,
                    designation='TEAM_LEAD',
                    is_active=True,
                    tracker_pace=instance
                )
                logger.info(f"Auto-created Employee '{employee.name}' from Pace '{instance.name}'")
            except Employee.MultipleObjectsReturned:
                logger.warning(f"Multiple employees named '{instance.name}' exist. Manual linking required.")
        else:
            # Update existing linked employee if name changed
            try:
                employee = Employee.objects.get(tracker_pace=instance)
                if employee.name != instance.name:
                    logger.info(f"Updating employee name from '{employee.name}' to '{instance.name}'")
                    employee.name = instance.name
                    employee.save()
            except Employee.DoesNotExist:
                logger.info(f"Pace '{instance.name}' updated but no linked employee found")
    except Exception as e:
        logger.error(f"Error syncing Pace '{instance.name}' to Employee: {str(e)}")
