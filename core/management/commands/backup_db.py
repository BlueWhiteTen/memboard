import gzip
import io
from datetime import datetime

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand

BACKUP_PREFIX = 'backups/'
DEFAULT_RETENTION = 14  # keep this many most-recent backups


class Command(BaseCommand):
    help = (
        "Dump the full database to a gzip-compressed JSON fixture and store it "
        "under the app's default file storage (backups/ prefix), pruning old "
        "backups beyond the retention window. Intended to run once a day "
        "(e.g. via a Render Cron Job: `python manage.py backup_db`)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep', type=int, default=DEFAULT_RETENTION,
            help=f'How many most-recent backups to retain (default {DEFAULT_RETENTION}).',
        )

    def handle(self, *args, **options):
        keep = options['keep']
        timestamp = datetime.utcnow().strftime('%Y-%m-%d_%H%M%S')
        filename = f'{BACKUP_PREFIX}memboard_{timestamp}.json.gz'

        self.stdout.write('Dumping database...')
        raw = io.StringIO()
        call_command(
            'dumpdata',
            exclude=['contenttypes', 'auth.permission', 'sessions.session', 'admin.logentry'],
            use_natural_foreign_keys=True,
            stdout=raw,
        )
        compressed = gzip.compress(raw.getvalue().encode('utf-8'))

        default_storage.save(filename, ContentFile(compressed))
        size_kb = len(compressed) / 1024
        self.stdout.write(self.style.SUCCESS(f'Backup written: {filename} ({size_kb:.1f} KB)'))

        self._prune_old_backups(keep)

    def _prune_old_backups(self, keep):
        try:
            _, files = default_storage.listdir(BACKUP_PREFIX)
        except FileNotFoundError:
            return
        backups = sorted(f for f in files if f.startswith('memboard_') and f.endswith('.json.gz'))
        excess = len(backups) - keep
        if excess <= 0:
            return
        for old in backups[:excess]:
            path = BACKUP_PREFIX + old
            default_storage.delete(path)
            self.stdout.write(f'Pruned old backup: {path}')
