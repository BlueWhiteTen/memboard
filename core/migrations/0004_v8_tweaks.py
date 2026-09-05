from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_v8_additions'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='memory_delete_permission',
            field=models.CharField(
                choices=[('creator_only', 'Only the person who added it'), ('all_members', 'Any board member')],
                default='creator_only', max_length=15,
            ),
        ),
        migrations.AddField(
            model_name='group',
            name='board_delete_permission',
            field=models.CharField(
                choices=[('owner_only', 'Only the board owner'), ('all_members', 'Any board member')],
                default='owner_only', max_length=15,
            ),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='theme',
            field=models.CharField(
                choices=[('system', 'Match system'), ('light', 'Light'), ('dark', 'Dark')],
                default='system', max_length=10,
            ),
        ),
    ]
