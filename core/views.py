from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
import json

from .models import (
    Group, Memory, Friendship, FriendRequest, UserProfile,
    GroupInvite, Reaction, Comment, Notification, ActivityLog,
    FriendGroup, BoardJoinRequest,
    FONT_CHOICES, REACTION_CHOICES, COLOUR_CHOICES, THEME_CHOICES, PRIVACY_CHOICES,
    MEMORY_DELETE_PERMISSION_CHOICES, BOARD_DELETE_PERMISSION_CHOICES,
)
from .forms import (
    RegisterForm, EmailAuthenticationForm, GroupForm, GroupCoverForm,
    MemoryForm, EditMemoryForm, InviteMemberForm, FriendRequestForm,
    GroupSettingsForm, FriendGroupForm,
)
from .email_utils import send_invite_email
from .on_this_day import get_on_this_day_memories


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_initials(user):
    fn = (user.first_name or '').strip()
    ln = (user.last_name  or '').strip()
    if fn and ln:
        return (fn[0] + ln[0]).upper()
    if fn:
        return fn[:2].upper()
    return user.email[:2].upper()


def get_display_name(user):
    full = f"{user.first_name} {user.last_name}".strip()
    return full if full else user.email


def annotate_users(users):
    for u in users:
        u.initials     = get_initials(u)
        u.display_name = get_display_name(u)
    return users


def create_notification(recipient, actor, notif_type, text, memory=None, group=None):
    if recipient == actor:
        return
    Notification.objects.create(
        recipient=recipient, actor=actor, notif_type=notif_type,
        text=text, memory=memory, group=group,
    )


def log_activity(group, actor, action_type, description, memory=None):
    ActivityLog.objects.create(
        group=group, actor=actor, action_type=action_type,
        description=description, memory=memory,
    )


def _visible_user_ids_for(group, privacy, visible_to_group_id):
    """Which user ids would see `group` as a 'Shared with me' listing under
    the given (privacy, visible_to_group_id) combination — used to diff
    old vs. new state after a settings change."""
    if privacy == 'all_friends':
        return set(Friendship.get_friends(group.owner).values_list('pk', flat=True))
    if privacy == 'friend_group' and visible_to_group_id:
        return set(FriendGroup.objects.filter(pk=visible_to_group_id)
                   .values_list('members__pk', flat=True)) - {None}
    return set()


def notify_newly_visible_users(group, old_privacy, old_visible_to_group_id):
    """After a board's privacy settings change, notify anyone who can newly
    see it (and isn't already a member) that it's been shared with them."""
    old_visible = _visible_user_ids_for(group, old_privacy, old_visible_to_group_id)
    new_visible = _visible_user_ids_for(group, group.privacy, group.visible_to_group_id)
    member_ids  = set(group.members.values_list('pk', flat=True))
    for uid in (new_visible - old_visible) - member_ids:
        try:
            u = User.objects.get(pk=uid)
        except User.DoesNotExist:
            continue
        create_notification(
            u, group.owner, 'board_visible',
            f'{get_display_name(group.owner)} shared the board "{group.name}" with you',
            group=group,
        )


def notify_boards_visible_after_friendship(user_a, user_b):
    """When two people become friends, any 'all friends' boards either of
    them owns become newly visible to the other."""
    for owner, viewer in ((user_a, user_b), (user_b, user_a)):
        boards = Group.objects.filter(owner=owner, privacy='all_friends').exclude(members=viewer)
        for board in boards:
            create_notification(
                viewer, owner, 'board_visible',
                f'{get_display_name(owner)} shared the board "{board.name}" with you',
                group=board,
            )


# ── Auth ──────────────────────────────────────────────────────────────────────

@ratelimit(key='ip', rate='10/h', method='POST', block=False)
def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    invite_token = request.GET.get('invite') or request.POST.get('invite_token')
    if request.method == 'POST' and getattr(request, 'limited', False):
        return render(request, 'core/register.html', {
            'form': RegisterForm(), 'invite_token': invite_token, 'rate_limited': True,
        })
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        UserProfile.objects.get_or_create(user=user)
        if invite_token:
            try:
                invite = GroupInvite.objects.get(
                    token=invite_token, email__iexact=user.email, accepted=False)
                invite.group.members.add(user)
                invite.accepted = True
                invite.save()
                messages.success(request, f'You\'ve been added to "{invite.group.name}"!')
            except GroupInvite.DoesNotExist:
                pass
        if user.email:
            for inv in GroupInvite.objects.filter(email__iexact=user.email, accepted=False):
                inv.group.members.add(user)
                inv.accepted = True
                inv.save()
        login(request, user)
        messages.success(request, f"Welcome to Memboard, {user.first_name}!")
        return redirect('home')
    return render(request, 'core/register.html', {'form': form, 'invite_token': invite_token})


@ratelimit(key='ip', rate='15/5m', method='POST', block=False)
def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST' and getattr(request, 'limited', False):
        return render(request, 'core/login.html', {'form': EmailAuthenticationForm(), 'rate_limited': True})
    form = EmailAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(request.GET.get('next', 'home'))
    return render(request, 'core/login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('login')


# ── Home ──────────────────────────────────────────────────────────────────────

@login_required
def home_view(request):
    user = request.user
    user_groups    = (Group.objects.filter(members=user)
                      .annotate(memory_count=Count('memories', filter=Q(memories__is_deleted=False)))
                      .order_by('-created_at'))
    friends        = list(Friendship.get_friends(user))
    pending_in     = FriendRequest.objects.filter(to_user=user, accepted=False)
    total_memories = Memory.objects.filter(group__members=user, is_deleted=False).count()
    unread_notifs  = Notification.objects.filter(recipient=user, is_read=False).count()
    annotate_users(friends)

    # Shared-boards count on each friend chip.
    for f in friends:
        f.shared_boards = Group.objects.filter(members=user).filter(members=f).count()

    # Shared with me: boards visible via privacy settings that the user
    # hasn't joined yet — shown as a bare listing with a request-to-join action.
    candidates = (Group.objects
                  .exclude(members=user)
                  .filter(privacy__in=['all_friends', 'friend_group'])
                  .select_related('owner'))
    shared_with_me = [g for g in candidates if g.is_visible_to(user)]
    requested_ids  = set(BoardJoinRequest.objects.filter(requester=user).values_list('board_id', flat=True))
    for g in shared_with_me:
        g.already_requested = g.pk in requested_ids

    # On this day (preview for the home widget).
    on_this_day = get_on_this_day_memories(user)[:6]
    for m in on_this_day:
        m.creator_initials = get_initials(m.creator)
        m.creator_display  = get_display_name(m.creator)

    return render(request, 'core/home.html', {
        'user_groups':      user_groups,
        'friends':          friends,
        'pending_requests': pending_in,
        'total_memories':   total_memories,
        'unread_notifs':    unread_notifs,
        'shared_with_me':   shared_with_me,
        'on_this_day':      on_this_day,
        'user_initials':    get_initials(user),
        'user_display':     get_display_name(user),
    })


# ── Search ────────────────────────────────────────────────────────────────────

@login_required
def search_view(request):
    user  = request.user
    query = request.GET.get('q', '').strip()
    memories = []
    if query:
        memories = Memory.objects.filter(
            group__members=user, is_deleted=False
        ).filter(
            Q(title__icontains=query) | Q(content__icontains=query) |
            Q(location_name__icontains=query)
        ).select_related('group', 'creator').order_by('-created_at')
        for m in memories:
            m.creator_initials = get_initials(m.creator)
            m.creator_display  = get_display_name(m.creator)
    return render(request, 'core/search.html', {
        'query':         query,
        'memories':      memories,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


# ── Notifications ─────────────────────────────────────────────────────────────

@login_required
def notifications_view(request):
    user   = request.user
    notifs = Notification.objects.filter(recipient=user).select_related('actor', 'memory', 'group')
    Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)
    for n in notifs:
        if n.actor:
            n.actor.initials     = get_initials(n.actor)
            n.actor.display_name = get_display_name(n.actor)
    return render(request, 'core/notifications.html', {
        'notifs':        notifs,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


@login_required
def mark_notif_read_view(request, pk):
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.is_read = True
    notif.save()
    return JsonResponse({'ok': True})


# ── Groups ────────────────────────────────────────────────────────────────────

@login_required
def create_group_view(request):
    user         = request.user
    friends      = annotate_users(list(Friendship.get_friends(user)))
    friend_groups = FriendGroup.objects.filter(owner=user).prefetch_related('members')
    if request.method == 'POST':
        form = GroupForm(request.POST, request.FILES, owner=user)
        if form.is_valid():
            group = form.save(commit=False)
            group.owner = user
            group.save()
            for fid in request.POST.getlist('selected_friends'):
                try:
                    friend = User.objects.get(pk=fid)
                    if Friendship.are_friends(user, friend):
                        group.members.add(friend)
                except User.DoesNotExist:
                    pass
            log_activity(group, user, 'member_join', f'{get_display_name(user)} created the board')
            messages.success(request, f'Board "{group.name}" created!')
            return redirect('group_detail', pk=group.pk)
    else:
        form = GroupForm(owner=user)
    return render(request, 'core/create_group.html', {
        'form': form, 'friends': friends, 'friend_groups': friend_groups,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


@login_required
def group_detail_view(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.user not in group.members.all():
        messages.error(request, "You're not a member of that board.")
        return redirect('home')

    user     = request.user
    memories = (group.memories
                .filter(is_deleted=False)
                .select_related('creator')
                .prefetch_related('tagged', 'reactions', 'comments'))

    for memory in memories:
        memory.user_can_edit    = memory.can_edit(user)
        memory.user_can_delete  = memory.can_delete(user)
        memory.creator_initials = get_initials(memory.creator)
        memory.creator_display  = get_display_name(memory.creator)
        memory.reaction_counts  = memory.reaction_summary()
        memory.user_reactions   = list(memory.reactions.filter(user=user).values_list('emoji', flat=True))
        memory.comment_count    = memory.comments.count()
        for t in memory.tagged.all():
            t.initials     = get_initials(t)
            t.display_name = get_display_name(t)

    other_members = annotate_users(list(group.members.exclude(pk=user.pk)))
    all_members   = annotate_users(list(group.members.all()))

    # Map memories (those with lat/lng)
    map_memories = [
        {'id': m.pk, 'title': m.title or m.content[:40],
         'lat': m.location_lat, 'lng': m.location_lng,
         'location': m.location_name}
        for m in memories if m.location_lat and m.location_lng
    ]

    # Activity log (last 20)
    activity_log = group.activity_logs.select_related('actor', 'memory')[:20]
    for a in activity_log:
        if a.actor:
            a.actor.initials     = get_initials(a.actor)
            a.actor.display_name = get_display_name(a.actor)

    profile, _ = UserProfile.objects.get_or_create(user=user)

    is_owner = group.owner == user
    friend_groups = FriendGroup.objects.filter(owner=user) if is_owner else FriendGroup.objects.none()
    join_requests = (group.join_requests.select_related('requester') if is_owner
                      else BoardJoinRequest.objects.none())
    for jr in join_requests:
        jr.requester.initials     = get_initials(jr.requester)
        jr.requester.display_name = get_display_name(jr.requester)

    # Recycle bin. With the default (creator-only) delete policy this is your
    # own deletions; if the board allows any member to delete, the bin is
    # shared so anyone who can restore a memory can see it there.
    if group.memory_delete_permission == 'all_members':
        trashed_memories = group.memories.filter(is_deleted=True).select_related('creator')
    else:
        trashed_memories = group.memories.filter(is_deleted=True, creator=user).select_related('creator')
    for m in trashed_memories:
        m.creator_display = get_display_name(m.creator)

    return render(request, 'core/group_detail.html', {
        'group':            group,
        'memories':         memories,
        'trashed_memories': trashed_memories,
        'other_members':    other_members,
        'all_members':      all_members,
        'note_font':        profile.note_font_css,
        'font_choices':     FONT_CHOICES,
        'current_font':     profile.note_font,
        'user_initials':    get_initials(user),
        'user_display':     get_display_name(user),
        'map_memories':     json.dumps(map_memories),
        'activity_log':     activity_log,
        'reaction_choices': REACTION_CHOICES,
        'colour_choices':   COLOUR_CHOICES,
        'is_owner':         is_owner,
        'can_delete_board': group.user_can_delete_board(user),
        'memory_delete_choices': MEMORY_DELETE_PERMISSION_CHOICES,
        'board_delete_choices':  BOARD_DELETE_PERMISSION_CHOICES,
        'privacy_choices':  PRIVACY_CHOICES,
        'friend_groups':    friend_groups,
        'join_requests':    join_requests,
    })


@login_required
def update_cover_view(request, pk):
    group = get_object_or_404(Group, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = GroupCoverForm(request.POST, request.FILES, instance=group)
        if form.is_valid():
            form.save()
            log_activity(group, request.user, 'cover_changed',
                         f'{get_display_name(request.user)} updated the board cover')
            return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=400)


@login_required
def set_font_view(request):
    if request.method == 'POST':
        font  = request.POST.get('font', 'dm_sans')
        valid = [f[0] for f in FONT_CHOICES]
        if font in valid:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            profile.note_font = font
            profile.save()
            return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=400)


@login_required
def set_theme_view(request):
    if request.method == 'POST':
        theme = request.POST.get('theme', 'system')
        valid = [t[0] for t in THEME_CHOICES]
        if theme in valid:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            profile.theme = theme
            profile.save(update_fields=['theme'])
            return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=400)


@login_required
def update_board_settings_view(request, pk):
    group = get_object_or_404(Group, pk=pk, owner=request.user)
    if request.method == 'POST':
        old_privacy  = group.privacy
        old_group_id = group.visible_to_group_id
        form = GroupSettingsForm(request.POST, instance=group, owner=request.user)
        if form.is_valid():
            form.save()
            notify_newly_visible_users(group, old_privacy, old_group_id)
            messages.success(request, "Board settings updated.")
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text())
    return redirect('group_detail', pk=pk)


@login_required
def invite_member_view(request, pk):
    group = get_object_or_404(Group, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = InviteMemberForm(request.POST, group=group)
        if form.is_valid():
            new_member = form._resolved_user
            group.members.add(new_member)
            log_activity(group, request.user, 'member_join',
                         f'{get_display_name(new_member)} was added to the board')
            create_notification(new_member, request.user, 'board_invite',
                                f'{get_display_name(request.user)} added you to "{group.name}"',
                                group=group)
            messages.success(request, f"{get_display_name(new_member)} added!")
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text())
    return redirect('group_detail', pk=pk)


@login_required
def invite_by_email_view(request, pk):
    group = get_object_or_404(Group, pk=pk, owner=request.user)
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if not email:
            return JsonResponse({'ok': False, 'error': 'No email provided.'}, status=400)
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            return JsonResponse({
                'ok': False,
                'error': f'{get_display_name(existing)} already has an account — use "Add to board".',
                'username': existing.username,
            }, status=400)
        if GroupInvite.objects.filter(group=group, email__iexact=email, accepted=False).exists():
            return JsonResponse({'ok': False, 'error': 'An invite was already sent to that address.'}, status=400)
        invite = GroupInvite.objects.create(group=group, invited_by=request.user, email=email)
        sent   = send_invite_email(request.user, email, group, invite.token)
        if sent:
            return JsonResponse({'ok': True, 'message': f'Invitation sent to {email}!'})
        else:
            invite.delete()
            return JsonResponse({'ok': False, 'error': 'Failed to send email. Check Gmail settings.'}, status=500)
    return JsonResponse({'ok': False}, status=405)


@login_required
def lookup_user_view(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'found': False})
    user = None
    if '@' in query:
        user = User.objects.filter(email__iexact=query).first()
    if not user:
        user = User.objects.filter(username__iexact=query).first()
    if not user:
        parts = query.split()
        if len(parts) >= 2:
            user = User.objects.filter(
                first_name__iexact=parts[0],
                last_name__iexact=' '.join(parts[1:])
            ).first()
    if user and user != request.user:
        return JsonResponse({
            'found':    True,
            'username': user.username,
            'name':     get_display_name(user),
            'initials': get_initials(user),
            'id':       user.id,
        })
    return JsonResponse({'found': False, 'message': 'No user found.'})


@login_required
def delete_group_view(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if not group.user_can_delete_board(request.user):
        messages.error(request, "You don't have permission to delete this board.")
        return redirect('group_detail', pk=pk)
    if request.method == 'POST':
        name = group.name
        group.delete()
        messages.success(request, f'Board "{name}" deleted.')
    return redirect('home')


@login_required
def request_join_board_view(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        if group.is_member(request.user):
            messages.info(request, "You're already a member of that board.")
        elif not group.is_visible_to(request.user):
            messages.error(request, "You don't have permission to request to join that board.")
        else:
            _, created = BoardJoinRequest.objects.get_or_create(board=group, requester=request.user)
            if created:
                create_notification(
                    group.owner, request.user, 'join_request',
                    f'{get_display_name(request.user)} asked to join "{group.name}"',
                    group=group,
                )
                messages.success(request, f'Request sent — {get_display_name(group.owner)} will need to approve it.')
            else:
                messages.info(request, "You already requested to join this board.")
    return redirect('home')


@login_required
def approve_join_request_view(request, pk, req_id):
    group    = get_object_or_404(Group, pk=pk, owner=request.user)
    join_req = get_object_or_404(BoardJoinRequest, pk=req_id, board=group)
    if request.method == 'POST':
        requester = join_req.requester
        group.members.add(requester)
        join_req.delete()
        log_activity(group, request.user, 'member_join', f'{get_display_name(requester)} joined the board')
        create_notification(
            requester, request.user, 'join_approved',
            f'{get_display_name(request.user)} approved your request to join "{group.name}"',
            group=group,
        )
        messages.success(request, f'{get_display_name(requester)} added to the board!')
    return redirect('group_detail', pk=pk)


@login_required
def decline_join_request_view(request, pk, req_id):
    group    = get_object_or_404(Group, pk=pk, owner=request.user)
    join_req = get_object_or_404(BoardJoinRequest, pk=req_id, board=group)
    if request.method == 'POST':
        join_req.delete()
        messages.info(request, "Join request declined.")
    return redirect('group_detail', pk=pk)


# ── Friend Groups ─────────────────────────────────────────────────────────────

@login_required
def friend_groups_view(request):
    user   = request.user
    groups = FriendGroup.objects.filter(owner=user).annotate(member_count=Count('members'))
    return render(request, 'core/friend_groups.html', {
        'friend_groups': groups,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


@login_required
def create_friend_group_view(request):
    user = request.user
    if request.method == 'POST':
        form = FriendGroupForm(request.POST)
        if form.is_valid():
            fg = form.save(commit=False)
            fg.owner = user
            try:
                fg.save()
            except Exception:
                form.add_error('name', 'You already have a group with that name.')
            else:
                messages.success(request, f'"{fg.name}" created — add friends to it below.')
                return redirect('friend_group_detail', pk=fg.pk)
    else:
        form = FriendGroupForm()
    return render(request, 'core/create_friend_group.html', {
        'form': form,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


@login_required
def friend_group_detail_view(request, pk):
    fg   = get_object_or_404(FriendGroup, pk=pk, owner=request.user)
    user = request.user
    current_member_ids = set(fg.members.values_list('pk', flat=True))

    if request.method == 'POST':
        form = FriendGroupForm(request.POST, instance=fg)
        if form.is_valid():
            form.save()

        valid_friend_ids = set(Friendship.get_friends(user).values_list('pk', flat=True))
        selected_ids = set()
        for fid in request.POST.getlist('selected_friends'):
            try:
                selected_ids.add(int(fid))
            except ValueError:
                pass
        new_member_ids = selected_ids & valid_friend_ids
        fg.members.set(new_member_ids)

        newly_added = new_member_ids - current_member_ids
        if newly_added:
            visible_boards = Group.objects.filter(
                owner=user, privacy='friend_group', visible_to_group=fg)
            for uid in newly_added:
                try:
                    newly_member = User.objects.get(pk=uid)
                except User.DoesNotExist:
                    continue
                for board in visible_boards.exclude(members=newly_member):
                    create_notification(
                        newly_member, user, 'board_visible',
                        f'{get_display_name(user)} shared the board "{board.name}" with you',
                        group=board,
                    )
        messages.success(request, f'"{fg.name}" updated.')
        return redirect('friend_group_detail', pk=fg.pk)

    friends = annotate_users(list(Friendship.get_friends(user)))
    for f in friends:
        f.in_group = f.pk in current_member_ids

    return render(request, 'core/friend_group_detail.html', {
        'friend_group': fg,
        'friends':      friends,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


@login_required
def delete_friend_group_view(request, pk):
    fg = get_object_or_404(FriendGroup, pk=pk, owner=request.user)
    if request.method == 'POST':
        name = fg.name
        # Boards that relied on this group for visibility fall back to "only members".
        Group.objects.filter(visible_to_group=fg).update(privacy='members', visible_to_group=None)
        fg.delete()
        messages.success(request, f'"{name}" deleted.')
    return redirect('friend_groups')


# ── Memories ──────────────────────────────────────────────────────────────────

@login_required
def add_memory_view(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.user not in group.members.all():
        messages.error(request, "You're not a member of that board.")
        return redirect('home')
    if request.method == 'POST':
        form = MemoryForm(request.POST, request.FILES, group=group)
        if form.is_valid():
            memory         = form.save(commit=False)
            memory.group   = group
            memory.creator = request.user
            memory.save()
            form.save_m2m()
            # Notify tagged users
            for tagged_user in memory.tagged.all():
                create_notification(
                    tagged_user, request.user, 'tag',
                    f'{get_display_name(request.user)} tagged you in a memory on "{group.name}"',
                    memory=memory, group=group,
                )
            log_activity(group, request.user, 'memory_add',
                         f'{get_display_name(request.user)} added a memory: {memory.title or memory.content[:40]}',
                         memory=memory)
            messages.success(request, "Memory saved!")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    return redirect('group_detail', pk=pk)


@login_required
def edit_memory_view(request, pk):
    memory = get_object_or_404(Memory, pk=pk, is_deleted=False)
    if not memory.can_edit(request.user):
        messages.error(request, "You don't have permission to edit that memory.")
        return redirect('group_detail', pk=memory.group.pk)
    if request.method == 'POST':
        form = EditMemoryForm(request.POST, request.FILES, instance=memory, group=memory.group)
        if form.is_valid():
            form.save()
            log_activity(memory.group, request.user, 'memory_edit',
                         f'{get_display_name(request.user)} edited a memory: {memory.title or memory.content[:40]}',
                         memory=memory)
            messages.success(request, "Memory updated!")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    return redirect('group_detail', pk=memory.group.pk)


@login_required
def delete_memory_view(request, pk):
    memory   = get_object_or_404(Memory, pk=pk, is_deleted=False)
    group_pk = memory.group.pk
    if not memory.can_delete(request.user):
        messages.error(request, "You don't have permission to delete that memory.")
        return redirect('group_detail', pk=group_pk)
    if request.method == 'POST':
        log_activity(memory.group, request.user, 'memory_delete',
                     f'{get_display_name(request.user)} deleted a memory: {memory.title or memory.content[:40]}')
        memory.is_deleted = True
        memory.deleted_at = timezone.now()
        memory.save(update_fields=['is_deleted', 'deleted_at'])
        messages.success(request, "Memory moved to the recycle bin — it'll be kept for 30 days.")
    return redirect('group_detail', pk=group_pk)


@login_required
def restore_memory_view(request, pk):
    memory   = get_object_or_404(Memory, pk=pk, is_deleted=True)
    group_pk = memory.group.pk
    can_restore = (memory.creator == request.user) or (
        memory.group.memory_delete_permission == 'all_members'
        and memory.group.members.filter(pk=request.user.pk).exists()
    )
    if not can_restore:
        messages.error(request, "You don't have permission to restore that memory.")
        return redirect('group_detail', pk=group_pk)
    if request.method == 'POST':
        memory.is_deleted = False
        memory.deleted_at = None
        memory.save(update_fields=['is_deleted', 'deleted_at'])
        log_activity(memory.group, request.user, 'memory_add',
                     f'{get_display_name(request.user)} restored a memory from the recycle bin')
        messages.success(request, "Memory restored!")
    return redirect('group_detail', pk=group_pk)


@login_required
def leave_board_view(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        if group.owner == request.user:
            messages.error(request, "Board owners can't leave — delete the board instead, or transfer ownership first.")
        elif request.user not in group.members.all():
            messages.error(request, "You're not a member of that board.")
        else:
            group.members.remove(request.user)
            log_activity(group, request.user, 'member_leave',
                         f'{get_display_name(request.user)} left the board')
            messages.success(request, f'You left "{group.name}".')
            return redirect('home')
    return redirect('group_detail', pk=pk)


@login_required
@require_POST
def pin_memory_view(request, pk):
    memory = get_object_or_404(Memory, pk=pk, is_deleted=False)
    if request.user not in memory.group.members.all():
        return JsonResponse({'ok': False}, status=403)
    memory.is_pinned = not memory.is_pinned
    memory.save(update_fields=['is_pinned'])
    action = 'memory_pin' if memory.is_pinned else 'memory_unpin'
    desc   = f'{get_display_name(request.user)} {"pinned" if memory.is_pinned else "unpinned"} a memory'
    log_activity(memory.group, request.user, action, desc, memory=memory)
    if memory.is_pinned and memory.creator != request.user:
        create_notification(memory.creator, request.user, 'pin',
                            f'{get_display_name(request.user)} pinned your memory in "{memory.group.name}"',
                            memory=memory, group=memory.group)
    return JsonResponse({'ok': True, 'pinned': memory.is_pinned})


# ── Reactions ─────────────────────────────────────────────────────────────────

@login_required
@require_POST
def react_memory_view(request, pk):
    memory = get_object_or_404(Memory, pk=pk, is_deleted=False)
    if request.user not in memory.group.members.all():
        return JsonResponse({'ok': False}, status=403)
    data  = json.loads(request.body)
    emoji = data.get('emoji', '')
    valid_emojis = [e[0] for e in REACTION_CHOICES]
    if emoji not in valid_emojis:
        return JsonResponse({'ok': False, 'error': 'Invalid emoji'}, status=400)

    reaction, created = Reaction.objects.get_or_create(
        memory=memory, user=request.user, emoji=emoji)
    if not created:
        reaction.delete()
        added = False
    else:
        added = True
        if memory.creator != request.user:
            create_notification(
                memory.creator, request.user, 'reaction',
                f'{get_display_name(request.user)} reacted {emoji} to your memory in "{memory.group.name}"',
                memory=memory, group=memory.group,
            )
        log_activity(memory.group, request.user, 'reaction_add',
                     f'{get_display_name(request.user)} reacted {emoji} to a memory', memory=memory)

    return JsonResponse({'ok': True, 'added': added, 'counts': memory.reaction_summary()})


# ── Comments ──────────────────────────────────────────────────────────────────

@login_required
def comments_view(request, pk):
    memory = get_object_or_404(Memory, pk=pk, is_deleted=False)
    if request.user not in memory.group.members.all():
        return JsonResponse({'ok': False}, status=403)

    if request.method == 'POST':
        data    = json.loads(request.body)
        content = data.get('content', '').strip()
        if not content:
            return JsonResponse({'ok': False, 'error': 'Empty comment'}, status=400)
        comment = Comment.objects.create(memory=memory, author=request.user, content=content)
        log_activity(memory.group, request.user, 'comment_add',
                     f'{get_display_name(request.user)} commented on a memory', memory=memory)
        if memory.creator != request.user:
            create_notification(
                memory.creator, request.user, 'comment',
                f'{get_display_name(request.user)} commented on your memory in "{memory.group.name}"',
                memory=memory, group=memory.group,
            )
        return JsonResponse({
            'ok': True,
            'comment': {
                'id':           comment.pk,
                'content':      comment.content,
                'author':       get_display_name(request.user),
                'initials':     get_initials(request.user),
                'created_at':   comment.created_at.strftime('%b %d, %Y'),
                'can_delete':   True,
            }
        })

    # GET – fetch all comments
    comments = memory.comments.select_related('author')
    data = [
        {
            'id':         c.pk,
            'content':    c.content,
            'author':     get_display_name(c.author),
            'initials':   get_initials(c.author),
            'created_at': c.created_at.strftime('%b %d, %Y'),
            'can_delete': c.author == request.user,
        }
        for c in comments
    ]
    return JsonResponse({'ok': True, 'comments': data})


@login_required
@require_POST
def delete_comment_view(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user)
    comment.delete()
    return JsonResponse({'ok': True})


# ── Annual Recap ──────────────────────────────────────────────────────────────

@login_required
def annual_recap_view(request, year=None):
    from django.db.models.functions import TruncMonth
    user = request.user
    if year is None:
        year = timezone.now().year
    year = int(year)

    memories = Memory.objects.filter(
        group__members=user,
        created_at__year=year,
        is_deleted=False,
    ).select_related('group', 'creator').prefetch_related('reactions')

    # Stats
    total        = memories.count()
    boards_used  = memories.values('group').distinct().count()
    total_photos = memories.filter(photo__isnull=False).exclude(photo='').count()
    top_reactions = {}
    for m in memories:
        for emoji, count in m.reaction_summary().items():
            top_reactions[emoji] = top_reactions.get(emoji, 0) + count

    # By month
    by_month = {i: 0 for i in range(1, 13)}
    for m in memories:
        by_month[m.created_at.month] += 1

    # Pinned memories
    pinned = memories.filter(is_pinned=True)[:6]

    # Top boards
    top_boards = (memories.values('group__name', 'group__pk')
                  .annotate(count=Count('id'))
                  .order_by('-count')[:5])

    return render(request, 'core/annual_recap.html', {
        'year':          year,
        'total':         total,
        'boards_used':   boards_used,
        'total_photos':  total_photos,
        'top_reactions': sorted(top_reactions.items(), key=lambda x: -x[1])[:5],
        'by_month':      by_month,
        'pinned':        pinned,
        'top_boards':    top_boards,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
        'prev_year':     year - 1,
        'next_year':     year + 1 if year < timezone.now().year else None,
    })


# ── On This Day ───────────────────────────────────────────────────────────────

@login_required
def on_this_day_view(request):
    import calendar
    from datetime import date, timedelta

    user  = request.user
    today = timezone.localdate()
    try:
        month = int(request.GET.get('month', today.month))
        day   = int(request.GET.get('day', today.day))
    except ValueError:
        month, day = today.month, today.day
    month = min(max(month, 1), 12)
    day   = min(max(day, 1), calendar.monthrange(2000, month)[1])  # 2000 is a leap year

    memories = get_on_this_day_memories(user, month, day)
    for m in memories:
        m.creator_initials = get_initials(m.creator)
        m.creator_display  = get_display_name(m.creator)

    anchor    = date(2000, month, day)
    prev_date = anchor - timedelta(days=1)
    next_date = anchor + timedelta(days=1)

    return render(request, 'core/on_this_day.html', {
        'memories':     memories,
        'month':        month,
        'day':          day,
        'is_today':     (month == today.month and day == today.day),
        'display_date': f"{calendar.month_name[month]} {day}",
        'prev_month':   prev_date.month, 'prev_day': prev_date.day,
        'next_month':   next_date.month, 'next_day': next_date.day,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


# ── Friends ───────────────────────────────────────────────────────────────────

@login_required
def friends_view(request):
    user        = request.user
    friends     = list(Friendship.get_friends(user))
    pending_in  = FriendRequest.objects.filter(to_user=user, accepted=False).select_related('from_user')
    pending_out = FriendRequest.objects.filter(from_user=user, accepted=False).select_related('to_user')
    annotate_users(friends)
    for f in friends:
        f.shared_boards = Group.objects.filter(members=user).filter(members=f).count()
    for r in pending_in:
        r.from_user.initials     = get_initials(r.from_user)
        r.from_user.display_name = get_display_name(r.from_user)
    for r in pending_out:
        r.to_user.initials     = get_initials(r.to_user)
        r.to_user.display_name = get_display_name(r.to_user)
    return render(request, 'core/friends.html', {
        'friends':       friends,
        'pending_in':    pending_in,
        'pending_out':   pending_out,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


@login_required
def send_friend_request_view(request):
    if request.method == 'POST':
        form = FriendRequestForm(request.POST, from_user=request.user)
        if form.is_valid():
            FriendRequest.objects.get_or_create(
                from_user=request.user, to_user=form._resolved_user)
            create_notification(
                form._resolved_user, request.user, 'friend_req',
                f'{get_display_name(request.user)} sent you a friend request',
            )
            messages.success(request, f"Friend request sent to {get_display_name(form._resolved_user)}!")
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text())
    return redirect('friends')


@login_required
def accept_friend_request_view(request, request_id):
    freq = get_object_or_404(FriendRequest, pk=request_id, to_user=request.user)
    if request.method == 'POST':
        freq.accepted = True
        freq.save()
        Friendship.make_friends(freq.from_user, freq.to_user)
        notify_boards_visible_after_friendship(freq.from_user, freq.to_user)
        messages.success(request, f"You're now friends with {get_display_name(freq.from_user)}!")
    return redirect('friends')


@login_required
def decline_friend_request_view(request, request_id):
    freq = get_object_or_404(FriendRequest, pk=request_id, to_user=request.user)
    if request.method == 'POST':
        freq.delete()
    return redirect('friends')


@login_required
def remove_friend_view(request, user_id):
    other = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        u1, u2 = (request.user, other) if request.user.id < other.id else (other, request.user)
        Friendship.objects.filter(user1=u1, user2=u2).delete()
        messages.info(request, f"Removed {get_display_name(other)} from friends.")
    return redirect('friends')


@login_required
def friend_profile_view(request, user_id):
    friend = get_object_or_404(User, pk=user_id)
    user   = request.user
    if not Friendship.are_friends(user, friend):
        messages.error(request, "You're not friends with that person.")
        return redirect('friends')

    shared_boards = (Group.objects.filter(members=user).filter(members=friend)
                      .annotate(memory_count=Count('memories', filter=Q(memories__is_deleted=False))))
    mutual_ids     = set(Friendship.get_friends(user).values_list('pk', flat=True)) & \
                     set(Friendship.get_friends(friend).values_list('pk', flat=True))
    mutual_friends = annotate_users(list(User.objects.filter(pk__in=mutual_ids)))

    u1, u2 = (user, friend) if user.id < friend.id else (friend, user)
    friendship   = Friendship.objects.filter(user1=u1, user2=u2).first()
    friends_since = friendship.created_at if friendship else None

    return render(request, 'core/friend_profile.html', {
        'friend':          friend,
        'friend_initials': get_initials(friend),
        'friend_display':  get_display_name(friend),
        'shared_boards':   shared_boards,
        'mutual_friends':  mutual_friends,
        'friends_since':   friends_since,
        'user_initials':   get_initials(user),
        'user_display':    get_display_name(user),
    })


# ── PWA / Push ────────────────────────────────────────────────────────────────

def sw_view(request):
    """Serve the service worker JS with the correct content-type."""
    from django.http import HttpResponse
    from django.templatetags.static import static
    import os
    sw_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'core', 'static', 'core', 'sw.js'
    )
    try:
        with open(sw_path) as f:
            content = f.read()
    except FileNotFoundError:
        content = '// service worker placeholder'
    return HttpResponse(content, content_type='application/javascript')


def manifest_view(request):
    from django.http import JsonResponse
    manifest = {
        "name": "Memboard",
        "short_name": "Memboard",
        "description": "Your shared memory boards",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#F7F3EC",
        "theme_color": "#C97B2A",
        "icons": [
            {"src": "/static/core/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/core/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    return JsonResponse(manifest)


@login_required
@require_POST
def save_push_subscription_view(request):
    data     = json.loads(request.body)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.push_endpoint = data.get('endpoint', '')
    profile.push_p256dh   = data.get('keys', {}).get('p256dh', '')
    profile.push_auth     = data.get('keys', {}).get('auth', '')
    profile.save(update_fields=['push_endpoint', 'push_p256dh', 'push_auth'])
    return JsonResponse({'ok': True})
