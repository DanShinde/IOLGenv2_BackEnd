from django.core.management.base import BaseCommand
from home.models import ForumCategory, ForumTag


class Command(BaseCommand):
    help = 'Create initial forum categories and tags'

    def handle(self, *args, **kwargs):
        categories_data = [
            {
                'name': 'General Discussion',
                'slug': 'general-discussion',
                'description': 'General topics and discussions about the platform',
                'icon': 'fa-comments',
                'color': '#667eea',
                'order': 1
            },
            {
                'name': 'Bug Reports',
                'slug': 'bug-reports',
                'description': 'Report bugs and issues you encounter',
                'icon': 'fa-bug',
                'color': '#f56565',
                'order': 2
            },
            {
                'name': 'Feature Requests',
                'slug': 'feature-requests',
                'description': 'Suggest new features and improvements',
                'icon': 'fa-lightbulb',
                'color': '#f6ad55',
                'order': 3
            },
            {
                'name': 'Inventory',
                'slug': 'inventory',
                'description': 'Discussions about the inventory management system',
                'icon': 'fa-boxes',
                'color': '#48bb78',
                'order': 4
            },
            {
                'name': 'Planner',
                'slug': 'planner',
                'description': 'Topics related to the project planner',
                'icon': 'fa-calendar-alt',
                'color': '#4299e1',
                'order': 5
            },
            {
                'name': 'Tracker',
                'slug': 'tracker',
                'description': 'Discussions about the tracking system',
                'icon': 'fa-chart-line',
                'color': '#9f7aea',
                'order': 6
            },
            {
                'name': 'Help & Support',
                'slug': 'help-support',
                'description': 'Get help and support from the community',
                'icon': 'fa-question-circle',
                'color': '#38b2ac',
                'order': 7
            },
        ]

        tags_data = [
            {'name': 'urgent', 'slug': 'urgent', 'color': '#dc2626'},
            {'name': 'enhancement', 'slug': 'enhancement', 'color': '#2563eb'},
            {'name': 'question', 'slug': 'question', 'color': '#16a34a'},
            {'name': 'documentation', 'slug': 'documentation', 'color': '#9333ea'},
            {'name': 'ui', 'slug': 'ui', 'color': '#ea580c'},
            {'name': 'backend', 'slug': 'backend', 'color': '#0891b2'},
            {'name': 'frontend', 'slug': 'frontend', 'color': '#c026d3'},
            {'name': 'performance', 'slug': 'performance', 'color': '#65a30d'},
            {'name': 'security', 'slug': 'security', 'color': '#dc2626'},
        ]

        created_categories = 0
        updated_categories = 0

        for cat_data in categories_data:
            category, created = ForumCategory.objects.get_or_create(
                slug=cat_data['slug'],
                defaults=cat_data
            )
            if created:
                created_categories += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created category: {category.name}')
                )
            else:
                # Update existing category
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
            tag, created = ForumTag.objects.get_or_create(
                slug=tag_data['slug'],
                defaults=tag_data
            )
            if created:
                created_tags += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created tag: {tag.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary:\n'
                f'  Categories created: {created_categories}\n'
                f'  Categories updated: {updated_categories}\n'
                f'  Tags created: {created_tags}'
            )
        )
