from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Notification
from core.on_this_day import get_on_this_day_memories


class Command(BaseCommand):
    help = (
        "Creates an 'on this day' notification for every user who has memories "
        "matching today's date from a previous year. Intended to run once a day "
        "(e.g. via crontab, alongside backup_db and purge_deleted_memories)."
    )

    def handle(self, *args, **options):
        today   = timezone.localdate()
        created = 0

        for user in User.objects.filter(is_active=True):
            already_sent = Notification.objects.filter(
                recipient=user, notif_type='on_this_day', created_at__date=today,
            ).exists()
            if already_sent:
                continue

            memories = get_on_this_day_memories(user)
            if not memories:
                continue

            years = sorted({m.on_this_day_year for m in memories}, reverse=True)
            year_text = ', '.join(str(y) for y in years[:3])
            count = len(memories)
            text = (
                f"You have {count} memor{'y' if count == 1 else 'ies'} "
                f"on this day from {year_text}"
            )
            Notification.objects.create(
                recipient=user, actor=None, notif_type='on_this_day', text=text,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Sent {created} "on this day" notification(s).'
        ))
