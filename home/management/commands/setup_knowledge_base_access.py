from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

KB_GROUP_NAME = 'Knowledge Base'


class Command(BaseCommand):
    help = (
        "Create the 'Knowledge Base' access group and add every currently-active "
        "user to it, so enabling KnowledgeBaseGroupRequiredMiddleware doesn't lock "
        "out anyone who already uses the Knowledge Base. Safe to re-run."
    )

    def handle(self, *args, **kwargs):
        group, created = Group.objects.get_or_create(name=KB_GROUP_NAME)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created group: {group.name}"))
        else:
            self.stdout.write(f"Group already exists: {group.name}")

        User = get_user_model()
        active_users = User.objects.filter(is_active=True)
        existing_member_ids = set(group.user_set.values_list('id', flat=True))
        to_add = active_users.exclude(id__in=existing_member_ids)
        added_count = to_add.count()
        if added_count:
            group.user_set.add(*to_add)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSummary:\n"
                f"  Group: {group.name}\n"
                f"  Active users added: {added_count}\n"
                f"  Total members now: {group.user_set.count()}"
            )
        )
