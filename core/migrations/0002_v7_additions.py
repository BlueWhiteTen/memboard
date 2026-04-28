from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # Add new fields to UserProfile
        migrations.AddField(
            model_name='userprofile',
            name='push_endpoint',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='push_p256dh',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='push_auth',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='weekly_digest',
            field=models.BooleanField(default=True),
        ),
        # Add cover_photo to Group
        migrations.AddField(
            model_name='group',
            name='cover_photo',
            field=models.ImageField(blank=True, null=True, upload_to='covers/'),
        ),
        # Add new fields to Memory
        migrations.AddField(
            model_name='memory',
            name='memory_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='memory',
            name='location_name',
            field=models.CharField(blank=True, max_length=255, default=''),
        ),
        migrations.AddField(
            model_name='memory',
            name='location_lat',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='memory',
            name='location_lng',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='memory',
            name='is_pinned',
            field=models.BooleanField(default=False),
        ),
        # Update Memory ordering
        migrations.AlterModelOptions(
            name='memory',
            options={'ordering': ['-is_pinned', '-created_at']},
        ),
        # Create new tables
        migrations.CreateModel(
            name='Reaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('emoji', models.CharField(max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('memory', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='core.memory')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='auth.user')),
            ],
            options={'unique_together': {('memory', 'user', 'emoji')}},
        ),
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('content', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='auth.user')),
                ('memory', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='core.memory')),
            ],
            options={'ordering': ['created_at']},
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('notif_type', models.CharField(max_length=20)),
                ('text', models.CharField(max_length=300)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='acted_notifications', to='auth.user')),
                ('group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.group')),
                ('memory', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.memory')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='auth.user')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('action_type', models.CharField(max_length=30)),
                ('description', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activity_logs', to='core.group')),
                ('memory', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.memory')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
