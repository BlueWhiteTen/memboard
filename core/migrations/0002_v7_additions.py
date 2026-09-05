from django.db import migrations


class Migration(migrations.Migration):
    """
    This migration used to add the v7 fields and tables (UserProfile push
    fields, Group.cover_photo, Memory location/pin fields, and the Reaction/
    Comment/Notification/ActivityLog models). At some point 0001_initial was
    regenerated to already include all of that schema, which left every
    operation here as an exact duplicate — `python manage.py migrate` failed
    on any fresh database with `OperationalError: duplicate column name: ...`
    (first hit on cover_photo, then memory_date, then the rest).

    Any database where this migration was already recorded as applied is
    untouched by turning its operations into a no-op — the columns and
    tables it used to create already exist there. Kept as a placeholder
    (rather than deleted) so migration history and dependencies stay intact
    for anything already deployed.
    """

    dependencies = [
        ('core', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = []
