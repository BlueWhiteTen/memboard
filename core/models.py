import random
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


# ── Friends ───────────────────────────────────────────────────────────────────

class FriendRequest(models.Model):
    from_user  = models.ForeignKey(User, related_name='sent_requests', on_delete=models.CASCADE)
    to_user    = models.ForeignKey(User, related_name='received_requests', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted   = models.BooleanField(default=False)

    class Meta:
        unique_together = ('from_user', 'to_user')

    def __str__(self):
        return f"{self.from_user} → {self.to_user} ({'accepted' if self.accepted else 'pending'})"


class Friendship(models.Model):
    user1      = models.ForeignKey(User, related_name='friendships_as_1', on_delete=models.CASCADE)
    user2      = models.ForeignKey(User, related_name='friendships_as_2', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user1', 'user2')

    def __str__(self):
        return f"{self.user1} & {self.user2}"

    @staticmethod
    def get_friends(user):
        qs1 = User.objects.filter(friendships_as_2__user1=user)
        qs2 = User.objects.filter(friendships_as_1__user2=user)
        return (qs1 | qs2).distinct()

    @staticmethod
    def are_friends(user1, user2):
        u1, u2 = (user1, user2) if user1.id < user2.id else (user2, user1)
        return Friendship.objects.filter(user1=u1, user2=u2).exists()

    @staticmethod
    def make_friends(user1, user2):
        u1, u2 = (user1, user2) if user1.id < user2.id else (user2, user1)
        Friendship.objects.get_or_create(user1=u1, user2=u2)


# ── Choices ───────────────────────────────────────────────────────────────────

FONT_CHOICES = [
    ('dm_sans',       'DM Sans'),
    ('lora',          'Lora'),
    ('caveat',        'Caveat'),
    ('courier_prime', 'Courier Prime'),
    ('patrick_hand',  'Patrick Hand'),
]

PRIVACY_CHOICES = [
    ('friends', 'Friends only'),
    ('invite',  'Invite only'),
    ('private', 'Just me'),
]

COLOUR_CHOICES = [
    ('yellow',   'Yellow'),
    ('green',    'Green'),
    ('blue',     'Blue'),
    ('pink',     'Pink'),
    ('lavender', 'Lavender'),
    ('peach',    'Peach'),
]

EDIT_PERMISSION_CHOICES = [
    ('only_me',     'Only me'),
    ('tagged',      'Me & tagged friends'),
    ('all_members', 'All board members'),
]

FONT_CSS = {
    'dm_sans':       "'DM Sans', sans-serif",
    'lora':          "'Lora', serif",
    'caveat':        "'Caveat', cursive",
    'courier_prime': "'Courier Prime', monospace",
    'patrick_hand':  "'Patrick Hand', cursive",
}

REACTION_CHOICES = [
    ('❤️',  'Heart'),
    ('😂',  'Laugh'),
    ('😮',  'Wow'),
    ('😢',  'Sad'),
    ('🔥',  'Fire'),
    ('🎉',  'Party'),
]

NOTIFICATION_TYPES = [
    ('reaction',     'Reaction on memory'),
    ('comment',      'Comment on memory'),
    ('tag',          'Tagged in memory'),
    ('friend_req',   'Friend request'),
    ('board_invite', 'Board invitation'),
    ('pin',          'Memory pinned'),
]

ACTIVITY_TYPES = [
    ('memory_add',     'Memory added'),
    ('memory_edit',    'Memory edited'),
    ('memory_delete',  'Memory deleted'),
    ('memory_pin',     'Memory pinned'),
    ('memory_unpin',   'Memory unpinned'),
    ('member_join',    'Member joined'),
    ('member_leave',   'Member left'),
    ('comment_add',    'Comment added'),
    ('reaction_add',   'Reaction added'),
    ('cover_changed',  'Cover photo changed'),
]


# ── User Profile ──────────────────────────────────────────────────────────────

class UserProfile(models.Model):
    user           = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    note_font      = models.CharField(max_length=20, choices=FONT_CHOICES, default='dm_sans')
    push_endpoint  = models.TextField(blank=True)
    push_p256dh    = models.TextField(blank=True)
    push_auth      = models.TextField(blank=True)
    weekly_digest  = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} profile"

    @property
    def note_font_css(self):
        return FONT_CSS.get(self.note_font, FONT_CSS['dm_sans'])


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


# ── Group ─────────────────────────────────────────────────────────────────────

class GroupInvite(models.Model):
    group       = models.ForeignKey('Group', related_name='pending_invites', on_delete=models.CASCADE)
    invited_by  = models.ForeignKey(User, related_name='sent_invites', on_delete=models.CASCADE)
    email       = models.EmailField()
    token       = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at  = models.DateTimeField(auto_now_add=True)
    accepted    = models.BooleanField(default=False)

    class Meta:
        unique_together = ('group', 'email')

    def __str__(self):
        return f"Invite to {self.group.name} → {self.email}"


class Group(models.Model):
    name        = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    privacy     = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default='friends')
    owner       = models.ForeignKey(User, related_name='owned_groups', on_delete=models.CASCADE)
    members     = models.ManyToManyField(User, related_name='member_groups', blank=True)
    cover_photo = models.ImageField(upload_to='covers/', blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.members.add(self.owner)


# ── Memory ────────────────────────────────────────────────────────────────────

class Memory(models.Model):
    group           = models.ForeignKey(Group, related_name='memories', on_delete=models.CASCADE)
    creator         = models.ForeignKey(User, related_name='created_memories', on_delete=models.CASCADE)
    tagged          = models.ManyToManyField(User, related_name='tagged_memories', blank=True)
    title           = models.CharField(max_length=200, blank=True)
    content         = models.TextField()
    colour          = models.CharField(max_length=10, choices=COLOUR_CHOICES, default='yellow')
    photo           = models.ImageField(upload_to='memories/', blank=True, null=True)
    rotation        = models.FloatField(default=0)
    edit_permission = models.CharField(max_length=15, choices=EDIT_PERMISSION_CHOICES, default='only_me')
    memory_date     = models.DateField(blank=True, null=True, help_text='When did this happen?')
    location_name   = models.CharField(max_length=255, blank=True, help_text='Place name')
    location_lat    = models.FloatField(blank=True, null=True)
    location_lng    = models.FloatField(blank=True, null=True)
    is_pinned       = models.BooleanField(default=False)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.group.name} – {self.title or self.content[:40]}"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.rotation = round(random.uniform(-2.0, 2.0), 2)
        super().save(*args, **kwargs)

    def can_edit(self, user):
        if user == self.creator:
            return True
        if self.edit_permission == 'only_me':
            return False
        if self.edit_permission == 'tagged':
            return self.tagged.filter(pk=user.pk).exists()
        if self.edit_permission == 'all_members':
            return self.group.members.filter(pk=user.pk).exists()
        return False

    def reaction_summary(self):
        """Returns dict of emoji → count."""
        from django.db.models import Count
        return {r['emoji']: r['count'] for r in
                self.reactions.values('emoji').annotate(count=Count('id'))}


# ── Reaction ──────────────────────────────────────────────────────────────────

class Reaction(models.Model):
    memory     = models.ForeignKey(Memory, related_name='reactions', on_delete=models.CASCADE)
    user       = models.ForeignKey(User, related_name='reactions', on_delete=models.CASCADE)
    emoji      = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('memory', 'user', 'emoji')

    def __str__(self):
        return f"{self.user} reacted {self.emoji} on {self.memory}"


# ── Comment ───────────────────────────────────────────────────────────────────

class Comment(models.Model):
    memory     = models.ForeignKey(Memory, related_name='comments', on_delete=models.CASCADE)
    author     = models.ForeignKey(User, related_name='comments', on_delete=models.CASCADE)
    content    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author} on {self.memory}: {self.content[:40]}"


# ── Notification ──────────────────────────────────────────────────────────────

class Notification(models.Model):
    recipient  = models.ForeignKey(User, related_name='notifications', on_delete=models.CASCADE)
    actor      = models.ForeignKey(User, related_name='acted_notifications', on_delete=models.CASCADE, null=True, blank=True)
    notif_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    memory     = models.ForeignKey(Memory, on_delete=models.CASCADE, null=True, blank=True)
    group      = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    text       = models.CharField(max_length=300)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"→ {self.recipient}: {self.text}"


# ── Activity Log ──────────────────────────────────────────────────────────────

class ActivityLog(models.Model):
    group       = models.ForeignKey(Group, related_name='activity_logs', on_delete=models.CASCADE)
    actor       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    description = models.CharField(max_length=300)
    memory      = models.ForeignKey(Memory, on_delete=models.SET_NULL, null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.group}] {self.actor}: {self.description}"
