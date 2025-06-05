from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from ioview.models import IOVProject, Tag, UserAccess

class Command(BaseCommand):
    help = 'Generate test user, project, tags, and user access for IOView'

    def handle(self, *args, **kwargs):
        User = get_user_model()

        # Create test user
        user, created = User.objects.get_or_create(
            username='john123',
            email='john@example.com',
            defaults={'first_name': 'John', 'last_name': 'Tester'}
        )
        if created:
            user.set_password('TempPass123!')
            user.save()
            self.stdout.write(self.style.SUCCESS('✔ Created test user: john123'))
        else:
            self.stdout.write('ℹ Test user already exists.')

        # Create test project
        project, created = IOVProject.objects.get_or_create(
            id=101,
            defaults={
                'name': 'Conveyor A',
                'plc_endpoint': 'opc.tcp://192.168.0.101:4840'
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✔ Created test project: Conveyor A'))
        else:
            self.stdout.write('ℹ Test project already exists.')

        # Create test tags
        tags_data = [
            {
                'name': 'Start Button',
                'type': 'DI',
                'address': 'ns=3;s=I0.0',
                'panel_number': 'P1',
                'location': 'Front Panel',
                'order': 1
            },
            {
                'name': 'Motor Run',
                'type': 'DO',
                'address': 'ns=3;s=Q0.0',
                'panel_number': 'P1',
                'location': 'Relay Cabinet',
                'order': 2
            }
        ]

        for tag_data in tags_data:
            tag, created = Tag.objects.get_or_create(project=project, name=tag_data['name'], defaults=tag_data)
            if created:
                self.stdout.write(self.style.SUCCESS(f"✔ Created tag: {tag.name}"))
            else:
                self.stdout.write(f"ℹ Tag already exists: {tag.name}")

        # Create user access entry
        access, created = UserAccess.objects.get_or_create(email=user.email)
        access.allowed_projects.add(project)
        self.stdout.write(self.style.SUCCESS(f"✔ Linked user to project: {project.name}"))
