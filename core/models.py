import random
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
# lazy, not gettext() — these CHOICES lists are built once at import/migration
# time, before any request (and its language) exists, so the translation has
# to happen lazily, at the point each label is actually displayed.
from django.utils.translation import gettext_lazy as _


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


# ── Friend Groups ─────────────────────────────────────────────────────────────
# A user's own way of clustering their friends — used to control who can see a
# board (privacy = 'friend_group'), and reusable anywhere else a friend picker
# needs a shortcut (e.g. adding a bunch of people to a new board at once).

class FriendGroup(models.Model):
    owner      = models.ForeignKey(User, related_name='friend_groups', on_delete=models.CASCADE)
    name       = models.CharField(max_length=80)
    members    = models.ManyToManyField(User, related_name='friend_group_memberships', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('owner', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.owner})"


# ── Choices ───────────────────────────────────────────────────────────────────

FONT_CHOICES = [
    ('dm_sans',       'DM Sans'),
    ('lora',          'Lora'),
    ('caveat',        'Caveat'),
    ('courier_prime', 'Courier Prime'),
    ('patrick_hand',  'Patrick Hand'),
]

PRIVACY_CHOICES = [
    ('private',      _('Just me')),
    ('members',      _('Only members')),
    ('friend_group', _('A specific friend group')),
    ('all_friends',  _('All my friends')),
]

COLOUR_CHOICES = [
    ('yellow',   _('Yellow')),
    ('green',    _('Green')),
    ('blue',     _('Blue')),
    ('pink',     _('Pink')),
    ('lavender', _('Lavender')),
    ('peach',    _('Peach')),
]

EDIT_PERMISSION_CHOICES = [
    ('only_me',     _('Only me')),
    ('tagged',      _('Me & tagged friends')),
    ('all_members', _('All board members')),
]

MEMORY_DELETE_PERMISSION_CHOICES = [
    ('creator_only', _('Only the person who added it')),
    ('all_members',  _('Any board member')),
]

BOARD_DELETE_PERMISSION_CHOICES = [
    ('owner_only',  _('Only the board owner')),
    ('all_members', _('Any board member')),
]

THEME_CHOICES = [
    ('system', _('Match system')),
    ('light',  _('Light')),
    ('dark',   _('Dark')),
]

BOARD_SORT_CHOICES = [
    ('recent',       _('Most recently updated')),
    ('alphabetical', _('Alphabetical')),
    ('custom',       _('Custom')),
]

# 'active' is the normal state. 'disabled' is a reversible pause the user
# chose themselves — logging back in returns them straight to 'active' with
# nothing touched. 'deleted' is permanent: set once, by delete_account_view,
# and never flipped back.
ACCOUNT_STATUS_CHOICES = [
    ('active',   'Active'),
    ('disabled', 'Disabled'),
    ('deleted',  'Deleted'),
]

# Keep in sync with settings.LANGUAGES — that list drives Django's own
# translation machinery, this one drives the profile field/switcher.
LANGUAGE_CHOICES = [
    ('en', 'English'),
    ('el', 'Ελληνικά'),
]

REPORT_REASON_CHOICES = [
    ('spam',          _('Spam or misleading')),
    ('inappropriate', _('Inappropriate or offensive')),
    ('harassment',    _('Harassment or bullying')),
    ('other',         _('Something else')),
]

PROFILE_VISIBILITY_CHOICES = [
    ('friends', _('Visible to friends')),
    ('private', _('Only me')),
]

FONT_CSS = {
    'dm_sans':       "'DM Sans', sans-serif",
    'lora':          "'Lora', serif",
    'caveat':        "'Caveat', cursive",
    'courier_prime': "'Courier Prime', monospace",
    'patrick_hand':  "'Patrick Hand', cursive",
}

REACTION_CHOICES = [
    ('😊',  _('Smile')),
    ('❤️',  _('Heart')),
    ('😂',  _('Laugh')),
    ('😮',  _('Wow')),
    ('😢',  _('Sad')),
    ('🔥',  _('Fire')),
    ('🎉',  _('Party')),
    ('👍',  _('Thumbs up')),
    ('😍',  _('Love it')),
    ('😆',  _('Haha')),
]

NOTIFICATION_TYPES = [
    ('reaction',      'Reaction on memory'),
    ('comment',       'Comment on memory'),
    ('tag',           'Tagged in memory'),
    ('friend_req',    'Friend request'),
    ('board_invite',  'Board invitation'),
    ('board_invite_pending', 'Board invitation (needs a response)'),
    ('pin',           'Memory pinned'),
    ('board_visible', 'Board shared with you'),
    ('join_request',  'Board join request'),
    ('join_approved', 'Join request approved'),
    ('on_this_day',   'On this day memories'),
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
    theme          = models.CharField(max_length=10, choices=THEME_CHOICES, default='light')

    # Powers the "Since your last visit" panel on the home page: set to now
    # every time home_view runs, so it always holds the *previous* visit's
    # timestamp while that view is building the page — null on a user's very
    # first visit, when there's nothing to compare against yet.
    last_seen_home_at = models.DateTimeField(null=True, blank=True)

    # Which order "Your Boards" is shown in on the home page — remembered
    # per-user rather than per-board, since two people sharing a board may
    # each want it sorted differently.
    board_sort_mode = models.CharField(max_length=15, choices=BOARD_SORT_CHOICES, default='recent')

    # Disable = "close for a bit": reversible, nothing is touched besides
    # this flag. Delete = permanent: the account is scrubbed and locked, but
    # the row itself is kept (never actually deleted) so content on boards
    # this person doesn't own can stay in place, anonymized, rather than
    # vanishing out from under everyone else on that board. See
    # get_display_name()/get_initials() in views.py for how that anonymized
    # display is applied everywhere.
    account_status = models.CharField(max_length=10, choices=ACCOUNT_STATUS_CHOICES, default='active')

    # Which language the site is shown in for this user — read by
    # core.middleware.ProfileLanguageMiddleware on every request so it's
    # remembered on every device they log into, same as theme/note_font.
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='en')

    # Personal info shown on the profile page — visible to friends or kept
    # private, controlled by info_visibility (one toggle for the whole bundle).
    bio             = models.CharField(max_length=200, blank=True, help_text="A short line about you")
    location        = models.CharField(max_length=100, blank=True)
    birthday        = models.DateField(null=True, blank=True)
    info_visibility = models.CharField(max_length=10, choices=PROFILE_VISIBILITY_CHOICES, default='friends')

    def __str__(self):
        return f"{self.user.username} profile"

    @property
    def note_font_css(self):
        return FONT_CSS.get(self.note_font, FONT_CSS['dm_sans'])

    @property
    def has_info(self):
        return bool(self.bio or self.location or self.birthday)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


# ── Group ─────────────────────────────────────────────────────────────────────

class GroupInvite(models.Model):
    group        = models.ForeignKey('Group', related_name='pending_invites', on_delete=models.CASCADE)
    invited_by   = models.ForeignKey(User, related_name='sent_invites', on_delete=models.CASCADE)
    email        = models.EmailField()
    # Set only when the invited email already belonged to a WorthKeeping account
    # at invite time — lets that person accept/decline from their
    # notifications instead of being added immediately. Left null for
    # invites to people who don't have an account yet (they join
    # automatically when they register via the emailed link).
    invited_user = models.ForeignKey(User, related_name='received_board_invites',
                                      on_delete=models.CASCADE, null=True, blank=True)
    token        = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at   = models.DateTimeField(auto_now_add=True)
    accepted     = models.BooleanField(default=False)

    class Meta:
        unique_together = ('group', 'email')

    def __str__(self):
        return f"Invite to {self.group.name} → {self.email}"


class FriendInvite(models.Model):
    """An email-based friend invite sent to someone who doesn't have a
    WorthKeeping account yet. They become friends automatically once they
    register with that email address."""
    from_user  = models.ForeignKey(User, related_name='sent_friend_invites', on_delete=models.CASCADE)
    email      = models.EmailField()
    token      = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted   = models.BooleanField(default=False)

    class Meta:
        unique_together = ('from_user', 'email')

    def __str__(self):
        return f"Friend invite from {self.from_user} → {self.email}"


class Group(models.Model):
    name        = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    privacy     = models.CharField(max_length=12, choices=PRIVACY_CHOICES, default='members')
    owner       = models.ForeignKey(User, related_name='owned_groups', on_delete=models.CASCADE)
    members     = models.ManyToManyField(User, related_name='member_groups', blank=True)
    admins      = models.ManyToManyField(User, related_name='admin_boards', blank=True,
                    help_text='Members promoted by the owner to help manage this board.')
    cover_photo = models.ImageField(upload_to='covers/', blank=True, null=True)
    # Vertical focal point for the cover photo crop, as a 0-100 percentage —
    # matches CSS object-position/background-position Y% semantics exactly,
    # so it applies consistently wherever the cover renders at a different
    # aspect ratio (the board header banner vs. the smaller board-tile strip
    # on the home page). 50 = centered (the old fixed behaviour).
    cover_focal_y = models.PositiveSmallIntegerField(default=50)
    created_at  = models.DateTimeField(auto_now_add=True)

    # Only used when privacy == 'friend_group': the one friend-group whose
    # members can see this board (as a listing) even before they join.
    visible_to_group = models.ForeignKey(
        FriendGroup, related_name='visible_boards', on_delete=models.SET_NULL,
        null=True, blank=True)

    memory_delete_permission = models.CharField(
        max_length=15, choices=MEMORY_DELETE_PERMISSION_CHOICES, default='creator_only')
    board_delete_permission = models.CharField(
        max_length=15, choices=BOARD_DELETE_PERMISSION_CHOICES, default='owner_only')

    # Set when a manager turns on the public, no-login read-only share link
    # for this board; cleared to turn sharing back off.
    share_token = models.UUIDField(null=True, blank=True, unique=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.members.add(self.owner)

    def user_can_delete_board(self, user):
        if user == self.owner:
            return True
        if self.board_delete_permission == 'all_members':
            return self.members.filter(pk=user.pk).exists()
        return False

    def is_member(self, user):
        return self.members.filter(pk=user.pk).exists()

    def is_admin(self, user):
        return self.admins.filter(pk=user.pk).exists()

    def can_manage(self, user):
        """Owner or admin — allowed to manage invites, join requests, and
        (once the owner has appointed them) other members' admin status."""
        return user == self.owner or self.is_admin(user)

    def is_visible_to(self, user):
        """Whether `user` can see this board at all — as a member, or as a
        bare listing under 'Shared with me' if the privacy settings allow it."""
        if user == self.owner or self.is_member(user):
            return True
        if self.privacy == 'all_friends':
            return Friendship.are_friends(self.owner, user)
        if self.privacy == 'friend_group' and self.visible_to_group_id:
            return self.visible_to_group.members.filter(pk=user.pk).exists()
        return False


class BoardOrder(models.Model):
    """Per-user placement for a board on that user's home dashboard — pin
    state and a custom drag position. Deliberately keyed by (user, group)
    rather than living on Group itself, since two people sharing a board
    may each want it pinned or ordered differently.

    A row here is only created once a user actually pins a board or drags
    it while in custom-sort mode — most boards never get one, and just fall
    back to the active sort mode's natural order (or, in custom mode, to
    the end of the list, ordered by when they were created)."""
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='board_orders')
    group      = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='user_orders')
    pinned     = models.BooleanField(default=False)
    sort_order = models.FloatField(default=0)

    class Meta:
        unique_together = ('user', 'group')

    def __str__(self):
        return f"{self.user} / {self.group} (pinned={self.pinned}, order={self.sort_order})"


class BoardJoinRequest(models.Model):
    """A request from a non-member who can see a board (via 'Shared with me')
    to actually join it. The board owner approves or declines it."""
    board      = models.ForeignKey(Group, related_name='join_requests', on_delete=models.CASCADE)
    requester  = models.ForeignKey(User, related_name='sent_join_requests', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('board', 'requester')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.requester} → {self.board.name}"


# ── Memory ────────────────────────────────────────────────────────────────────

class Memory(models.Model):
    group           = models.ForeignKey(Group, related_name='memories', on_delete=models.CASCADE)
    creator         = models.ForeignKey(User, related_name='created_memories', on_delete=models.CASCADE)
    tagged          = models.ManyToManyField(User, related_name='tagged_memories', blank=True)
    title           = models.CharField(max_length=200, blank=True)
    content         = models.TextField()
    colour          = models.CharField(max_length=10, choices=COLOUR_CHOICES, default='yellow')
    photo           = models.ImageField(upload_to='memories/', blank=True, null=True)
    video           = models.FileField(upload_to='memory_videos/', blank=True, null=True)
    voice_note      = models.FileField(upload_to='memory_voice/', blank=True, null=True)
    rotation        = models.FloatField(default=0)
    # Set when the creator (or board owner) turns on a public, no-login
    # read-only share link for this single memory.
    share_token     = models.UUIDField(null=True, blank=True, unique=True)
    edit_permission = models.CharField(max_length=15, choices=EDIT_PERMISSION_CHOICES, default='only_me')
    memory_date     = models.DateField(blank=True, null=True, help_text='When did this happen?')
    location_name   = models.CharField(max_length=255, blank=True, help_text='Place name')
    location_lat    = models.FloatField(blank=True, null=True)
    location_lng    = models.FloatField(blank=True, null=True)
    is_pinned       = models.BooleanField(default=False)
    is_deleted      = models.BooleanField(default=False)
    deleted_at      = models.DateTimeField(blank=True, null=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.group.name} – {self.title or self.content[:40]}"

    @property
    def days_left_in_trash(self):
        """Days remaining before this memory is permanently purged (soft delete only)."""
        if not self.is_deleted or not self.deleted_at:
            return None
        from django.utils import timezone
        elapsed = (timezone.now() - self.deleted_at).days
        return max(0, 30 - elapsed)

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

    def can_delete(self, user):
        if user == self.creator:
            return True
        if self.group.can_manage(user):
            return True
        if self.group.memory_delete_permission == 'all_members':
            return self.group.members.filter(pk=user.pk).exists()
        return False

    def can_share(self, user):
        """Who may turn this memory's public read-only link on/off."""
        return user == self.creator or self.group.can_manage(user)

    def reaction_summary(self):
        """Returns dict of emoji → count."""
        from django.db.models import Count
        return {r['emoji']: r['count'] for r in
                self.reactions.values('emoji').annotate(count=Count('id'))}

    def reaction_users(self):
        """Returns dict of emoji → list of User objects who reacted with it,
        in the order they reacted — used for the "who reacted" hover
        tooltip. Callers apply get_display_name() themselves so hidden/
        deleted-account labels stay consistent with the rest of the UI."""
        users = {}
        for r in self.reactions.select_related('user').order_by('created_at'):
            users.setdefault(r.emoji, []).append(r.user)
        return users

    def all_photo_urls(self):
        """The primary `photo` (if set) followed by any extra photos, in
        upload order — used by the gallery view of a memory."""
        urls = []
        if self.photo:
            urls.append(self.photo.url)
        urls += [p.photo.url for p in self.extra_photos.all()]
        return urls


class MemoryPhoto(models.Model):
    """Additional photos beyond a memory's single primary `photo` field —
    e.g. several shots from the same trip. Kept as a separate model rather
    than reworking Memory.photo, so existing memories/migrations are
    untouched."""
    memory     = models.ForeignKey(Memory, related_name='extra_photos', on_delete=models.CASCADE)
    photo      = models.ImageField(upload_to='memories/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Photo for {self.memory}"


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


# ── Memory Report ─────────────────────────────────────────────────────────────

class MemoryReport(models.Model):
    """A member flagging a memory as spam/inappropriate/etc. Stored for
    the record even though review currently happens by email (see
    email_utils.send_memory_report_email) — a board-admin-facing review
    queue can read straight from this table later without a new model."""
    memory     = models.ForeignKey(Memory, related_name='reports', on_delete=models.CASCADE)
    reporter   = models.ForeignKey(User, related_name='memory_reports', on_delete=models.CASCADE)
    reason     = models.CharField(max_length=20, choices=REPORT_REASON_CHOICES)
    details    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reporter} reported {self.memory} ({self.reason})"


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
