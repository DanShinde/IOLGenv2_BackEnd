from django.core.management.base import BaseCommand
from home.models import Category, Tag, Application


class Command(BaseCommand):
    help = 'Create initial knowledge base categories, tags, and applications'

    def handle(self, *args, **kwargs):
        categories_data = [
            {'name': 'Engineering', 'slug': 'engineering', 'description': 'Engineering documentation and standards'},
            {'name': 'HR', 'slug': 'hr', 'description': 'People ops and policy guides'},
            {'name': 'Design', 'slug': 'design', 'description': 'Design system and UX references'},
            {'name': 'Product', 'slug': 'product', 'description': 'Product specs and roadmaps'},
            {'name': 'Operations', 'slug': 'operations', 'description': 'Operational runbooks and processes'},
        ]

        tags_data = [
            {'name': 'urgent', 'slug': 'urgent', 'color': '#ef4444'},
            {'name': 'enhancement', 'slug': 'enhancement', 'color': '#3b82f6'},
            {'name': 'question', 'slug': 'question', 'color': '#22c55e'},
            {'name': 'documentation', 'slug': 'documentation', 'color': '#8b5cf6'},
            {'name': 'ui', 'slug': 'ui', 'color': '#f97316'},
            {'name': 'backend', 'slug': 'backend', 'color': '#0ea5e9'},
            {'name': 'frontend', 'slug': 'frontend', 'color': '#d946ef'},
            {'name': 'performance', 'slug': 'performance', 'color': '#84cc16'},
            {'name': 'security', 'slug': 'security', 'color': '#dc2626'},
        ]

        applications_data = [
            {'name': 'Auth Service', 'slug': 'auth-service', 'description': 'Authentication and access control'},
            {'name': 'Analytics Dashboard', 'slug': 'analytics-dashboard', 'description': 'Analytics and reporting'},
            {'name': 'Notification Service', 'slug': 'notification-service', 'description': 'Email and notification delivery'},
            {'name': 'Admin Portal', 'slug': 'admin-portal', 'description': 'Internal admin tooling'},
        ]

        created_categories = 0
        updated_categories = 0

        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(slug=cat_data['slug'], defaults=cat_data)
            if created:
                created_categories += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created category: {category.name}')
                )
            else:
                for key, value in cat_data.items():
                    if key != 'slug':
                        setattr(category, key, value)
                category.save()
                updated_categories += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated category: {category.name}')
                )

        created_tags = 0
        for tag_data in tags_data:
            tag, created = Tag.objects.get_or_create(slug=tag_data['slug'], defaults=tag_data)
            if created:
                created_tags += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created tag: {tag.name}')
                )

        created_apps = 0
        updated_apps = 0
        for app_data in applications_data:
            app, created = Application.objects.get_or_create(slug=app_data['slug'], defaults=app_data)
            if created:
                created_apps += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created application: {app.name}')
                )
            else:
                for key, value in app_data.items():
                    if key != 'slug':
                        setattr(app, key, value)
                app.save()
                updated_apps += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated application: {app.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary:\n'
                f'  Categories created: {created_categories}\n'
                f'  Categories updated: {updated_categories}\n'
                f'  Tags created: {created_tags}\n'
                f'  Applications created: {created_apps}\n'
                f'  Applications updated: {updated_apps}'
            )
        )
