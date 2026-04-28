from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='FriendRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('accepted', models.BooleanField(default=False)),
                ('from_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_requests', to='auth.user')),
                ('to_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='received_requests', to='auth.user')),
            ],
            options={'unique_together': {('from_user', 'to_user')}},
        ),
        migrations.CreateModel(
            name='Friendship',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user1', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='friendships_as_1', to='auth.user')),
                ('user2', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='friendships_as_2', to='auth.user')),
            ],
            options={'unique_together': {('user1', 'user2')}},
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note_font', models.CharField(choices=[('dm_sans', 'DM Sans'), ('lora', 'Lora'), ('caveat', 'Caveat'), ('courier_prime', 'Courier Prime'), ('patrick_hand', 'Patrick Hand')], default='dm_sans', max_length=20)),
                ('push_endpoint', models.TextField(blank=True)),
                ('push_p256dh', models.TextField(blank=True)),
                ('push_auth', models.TextField(blank=True)),
                ('weekly_digest', models.BooleanField(default=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to='auth.user')),
            ],
        ),
        migrations.CreateModel(
            name='Group',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True)),
                ('privacy', models.CharField(choices=[('friends', 'Friends only'), ('invite', 'Invite only'), ('private', 'Just me')], default='friends', max_length=10)),
                ('cover_photo', models.ImageField(blank=True, null=True, upload_to='covers/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='owned_groups', to='auth.user')),
                ('members', models.ManyToManyField(blank=True, related_name='member_groups', to='auth.user')),
            ],
        ),
        migrations.CreateModel(
            name='GroupInvite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField()),
                ('token', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('accepted', models.BooleanField(default=False)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pending_invites', to='core.group')),
                ('invited_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_invites', to='auth.user')),
            ],
            options={'unique_together': {('group', 'email')}},
        ),
        migrations.CreateModel(
            name='Memory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=200)),
                ('content', models.TextField()),
                ('colour', models.CharField(choices=[('yellow', 'Yellow'), ('green', 'Green'), ('blue', 'Blue'), ('pink', 'Pink'), ('lavender', 'Lavender'), ('peach', 'Peach')], default='yellow', max_length=10)),
                ('photo', models.ImageField(blank=True, null=True, upload_to='memories/')),
                ('rotation', models.FloatField(default=0)),
                ('edit_permission', models.CharField(choices=[('only_me', 'Only me'), ('tagged', 'Me & tagged friends'), ('all_members', 'All board members')], default='only_me', max_length=15)),
                ('memory_date', models.DateField(blank=True, null=True)),
                ('location_name', models.CharField(blank=True, max_length=255)),
                ('location_lat', models.FloatField(blank=True, null=True)),
                ('location_lng', models.FloatField(blank=True, null=True)),
                ('is_pinned', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_memories', to='auth.user')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memories', to='core.group')),
                ('tagged', models.ManyToManyField(blank=True, related_name='tagged_memories', to='auth.user')),
            ],
            options={'ordering': ['-is_pinned', '-created_at']},
        ),
        migrations.CreateModel(
            name='Reaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
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
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
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
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notif_type', models.CharField(choices=[('reaction', 'Reaction on memory'), ('comment', 'Comment on memory'), ('tag', 'Tagged in memory'), ('friend_req', 'Friend request'), ('board_invite', 'Board invitation'), ('pin', 'Memory pinned')], max_length=20)),
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
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(choices=[('memory_add', 'Memory added'), ('memory_edit', 'Memory edited'), ('memory_delete', 'Memory deleted'), ('memory_pin', 'Memory pinned'), ('memory_unpin', 'Memory unpinned'), ('member_join', 'Member joined'), ('member_leave', 'Member left'), ('comment_add', 'Comment added'), ('reaction_add', 'Reaction added'), ('cover_changed', 'Cover photo changed')], max_length=30)),
                ('description', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activity_logs', to='core.group')),
                ('memory', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.memory')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
