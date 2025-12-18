# planner/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from tracker.models import Project as TrackerProject
from employees.models import Employee
from .models import Project as PlannerProject, Segment
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=TrackerProject)
def create_or_update_planner_project(sender, instance, created, **kwargs):
    """
    When a tracker project is created, automatically create a corresponding planner project.
    When a tracker project is updated, sync the changes to planner if linked.
    """
    try:
        # Check if a planner project already exists for this tracker project
        try:
            planner_project = PlannerProject.objects.get(tracker_project=instance)
            # Update existing planner project
            planner_project.customer_name = instance.customer_name
            # Only update project_id if it's changed (be careful with unique constraint)
            if planner_project.project_id != instance.code:
                # Check if the new code already exists in planner
                if not PlannerProject.objects.filter(project_id=instance.code).exclude(id=planner_project.id).exists():
                    planner_project.project_id = instance.code

            # Sync segment if possible
            if instance.segment_con:
                segment, _ = Segment.objects.get_or_create(name=instance.segment_con.name)
                planner_project.segment = segment

            # Sync team lead/pace
            if instance.pace:
                try:
                    employee = Employee.objects.get(tracker_pace=instance.pace)
                    planner_project.team_lead = employee
                except Employee.DoesNotExist:
                    logger.warning(f"No planner employee linked to tracker pace: {instance.pace.name}")

            planner_project.save()
            logger.info(f"Updated planner project {planner_project.project_id} from tracker project {instance.code}")

        except PlannerProject.DoesNotExist:
            # Create new planner project only if created in tracker
            if created:
                # Check if a planner project with this code already exists
                if PlannerProject.objects.filter(project_id=instance.code).exists():
                    logger.warning(f"Planner project with code {instance.code} already exists. Skipping auto-creation.")
                    return

                # Get or create segment in planner
                segment = None
                if instance.segment_con:
                    segment, _ = Segment.objects.get_or_create(name=instance.segment_con.name)

                # Get team lead from planner if linked
                team_lead = None
                if instance.pace:
                    try:
                        team_lead = Employee.objects.get(tracker_pace=instance.pace)
                    except Employee.DoesNotExist:
                        logger.warning(f"No planner employee linked to tracker pace: {instance.pace.name}")

                # Create planner project
                planner_project = PlannerProject.objects.create(
                    project_id=instance.code,
                    customer_name=instance.customer_name,
                    segment=segment,
                    team_lead=team_lead,
                    tracker_project=instance
                )
                logger.info(f"Created planner project {planner_project.project_id} from tracker project {instance.code}")

    except Exception as e:
        logger.error(f"Error syncing tracker project {instance.code} to planner: {str(e)}")
