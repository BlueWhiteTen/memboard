from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Memory

RETENTION_DAYS = 30


class Command(BaseCommand):
    help = (
        "Permanently deletes memories that have been sitting in the recycle bin "
        f"for more than {RETENTION_DAYS} days, including their photo files. "
        "Intended to run once a day (e.g. via a Render Cron Job)."
    )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
        expired = Memory.objects.filter(is_deleted=True, deleted_at__lt=cutoff)
        count = expired.count()
        if not count:
            self.stdout.write('Nothing to purge.')
            return

        for memory in expired:
            if memory.photo:
                memory.photo.delete(save=False)
        deleted, _ = expired.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Purged {count} memor{"y" if count == 1 else "ies"} from the recycle bin.'
        ))
