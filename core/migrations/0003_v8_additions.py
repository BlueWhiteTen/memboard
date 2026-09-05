from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_v7_additions'),
    ]

    operations = [
        migrations.AddField(
            model_name='memory',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='memory',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
