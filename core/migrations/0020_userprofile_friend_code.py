from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_comment_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='friend_code',
            field=models.CharField(blank=True, db_index=True, max_length=32),
        ),
    ]
