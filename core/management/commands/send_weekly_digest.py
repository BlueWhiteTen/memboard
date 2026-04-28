from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from core.models import Memory
from core.email_utils import send_weekly_digest_email


class Command(BaseCommand):
    help = 'Send weekly memory digest emails to all users who opted in'

    def handle(self, *args, **options):
        one_week_ago = timezone.now() - timedelta(days=7)
        users = User.objects.filter(profile__weekly_digest=True, is_active=True)
        sent = 0
        for user in users:
            memories = Memory.objects.filter(
                group__members=user,
                created_at__gte=one_week_ago,
            ).select_related('group').order_by('-created_at')
            if memories.exists():
                if send_weekly_digest_email(user, list(memories)):
                    sent += 1
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} digest emails.'))
