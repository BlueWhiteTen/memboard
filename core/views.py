from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponseForbidden, Http404, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django import forms as django_forms
import io
import json
import os
import random
import uuid
import zipfile
from django.conf import settings

from .models import (
    Group, Memory, MemoryPhoto, Friendship, FriendRequest, UserProfile,
    GroupInvite, FriendInvite, Reaction, Comment, Notification, ActivityLog,
    FriendGroup, BoardJoinRequest,
    FONT_CHOICES, REACTION_CHOICES, COLOUR_CHOICES, THEME_CHOICES, PRIVACY_CHOICES,
    MEMORY_DELETE_PERMISSION_CHOICES, BOARD_DELETE_PERMISSION_CHOICES,
)
from .forms import (
    RegisterForm, EmailAuthenticationForm, GroupForm, GroupCoverForm,
    MemoryForm, EditMemoryForm, FriendRequestForm,
    GroupSettingsForm, FriendGroupForm, ProfileForm, ReportProblemForm,
)
from .email_utils import send_invite_email, send_friend_invite_email, send_problem_report_email
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


def get_user_stats(user):
    return {
        'memories_created': Memory.objects.filter(creator=user, is_deleted=False).count(),
        'boards_owned':     Group.objects.filter(owner=user).count(),
        'boards_joined':    Group.objects.filter(members=user).count(),
    }


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


def get_board_for_manager(pk, user):
    """Fetch a board the given user is allowed to manage (owner or
    admin) — used by the invite/join-request endpoints so admins get the
    same management powers as the owner, short of appointing other admins
    or deleting the board itself."""
    group = get_object_or_404(Group, pk=pk)
    if not group.can_manage(user):
        raise Http404("Not authorized to manage this board.")
    return group


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
            for finv in FriendInvite.objects.filter(email__iexact=user.email, accepted=False):
                Friendship.make_friends(finv.from_user, user)
                finv.accepted = True
                finv.save()
                notify_boards_visible_after_friendship(finv.from_user, user)
                create_notification(
                    finv.from_user, user, 'friend_req',
                    f'{get_display_name(user)} accepted your friend invite and joined Rememory!',
                )
        login(request, user)
        messages.success(request, f"Welcome to Rememory, {user.first_name}!")
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

    # Since your last visit: what changed across the user's boards since the
    # last time home_view ran for them. Null last_seen_home_at (first-ever
    # visit) means there's nothing to compare against yet, so skip it.
    profile, _ = UserProfile.objects.get_or_create(user=user)
    since_last_visit = []
    if profile.last_seen_home_at:
        since_last_visit = list(
            ActivityLog.objects
            .filter(group__members=user, created_at__gt=profile.last_seen_home_at)
            .exclude(actor=user)
            .select_related('actor', 'group')[:20]
        )
        for a in since_last_visit:
            if a.actor:
                a.actor.initials     = get_initials(a.actor)
                a.actor.display_name = get_display_name(a.actor)
    profile.last_seen_home_at = timezone.now()
    profile.save(update_fields=['last_seen_home_at'])

    return render(request, 'core/home.html', {
        'user_groups':       user_groups,
        'friends':           friends,
        'pending_requests':  pending_in,
        'total_memories':    total_memories,
        'unread_notifs':     unread_notifs,
        'shared_with_me':    shared_with_me,
        'on_this_day':       on_this_day,
        'since_last_visit':  since_last_visit,
        'user_initials':     get_initials(user),
        'user_display':      get_display_name(user),
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
        if n.notif_type == 'board_invite_pending' and n.group:
            pending = GroupInvite.objects.filter(group=n.group, invited_user=user, accepted=False).first()
            n.pending_invite_pk = pending.pk if pending else None
    return render(request, 'core/notifications.html', {
        'notifs':        notifs,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


@login_required
def report_problem_view(request):
    sent = False
    if request.method == 'POST':
        form = ReportProblemForm(request.POST)
        if form.is_valid():
            ok, _err = send_problem_report_email(request.user, form.cleaned_data['message'])
            if ok:
                sent = True
                form = ReportProblemForm()
            else:
                messages.error(request, "Couldn't send your report just now — please try again in a moment.")
    else:
        form = ReportProblemForm()
    return render(request, 'core/report_problem.html', {
        'form':          form,
        'sent':          sent,
        'user_initials': get_initials(request.user),
        'user_display':  get_display_name(request.user),
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

    user = request.user
    sort = request.GET.get('sort', 'newest')
    if sort not in ('newest', 'oldest', 'alphabetical'):
        sort = 'newest'

    # Filters — person tagged/created, colour, and a memory-date range.
    # Invalid/unparseable values are just dropped rather than erroring, so a
    # stale or hand-edited query string never breaks the board.
    filter_person = request.GET.get('person', '').strip()
    filter_colour = request.GET.get('colour', '').strip()
    filter_from   = request.GET.get('date_from', '').strip()
    filter_to     = request.GET.get('date_to', '').strip()
    search_query  = request.GET.get('q', '').strip()
    valid_colours = {c[0] for c in COLOUR_CHOICES}
    if filter_colour not in valid_colours:
        filter_colour = ''

    memories = (group.memories
                .filter(is_deleted=False)
                .select_related('creator')
                .prefetch_related('tagged', 'reactions', 'comments', 'extra_photos'))

    if filter_person.isdigit():
        pid = int(filter_person)
        memories = memories.filter(Q(tagged__pk=pid) | Q(creator__pk=pid)).distinct()
    else:
        filter_person = ''
    if filter_colour:
        memories = memories.filter(colour=filter_colour)
    if filter_from:
        memories = memories.filter(memory_date__gte=filter_from)
    if filter_to:
        memories = memories.filter(memory_date__lte=filter_to)
    if search_query:
        memories = memories.filter(Q(title__icontains=search_query) |
                                    Q(content__icontains=search_query) |
                                    Q(location_name__icontains=search_query))

    # Pinned memories always lead; the chosen sort applies within/after that.
    if sort == 'oldest':
        memories = memories.order_by('-is_pinned', 'created_at')
    elif sort == 'alphabetical':
        memories = memories.order_by('-is_pinned', 'title', 'content')
    # 'newest' uses the model's default ordering (-is_pinned, -created_at).

    for memory in memories:
        memory.user_can_edit    = memory.can_edit(user)
        memory.user_can_delete  = memory.can_delete(user)
        memory.user_can_share   = memory.can_share(user)
        memory.share_url = (request.build_absolute_uri(f'/shared/memory/{memory.share_token}/')
                             if memory.share_token else '')
        memory.creator_initials = get_initials(memory.creator)
        memory.creator_display  = get_display_name(memory.creator)
        memory.reaction_counts  = memory.reaction_summary()
        memory.user_reactions   = list(memory.reactions.filter(user=user).values_list('emoji', flat=True))
        memory.comment_count    = memory.comments.count()
        for t in memory.tagged.all():
            t.initials     = get_initials(t)
            t.display_name = get_display_name(t)

        # Card content is clamped to 2 lines (see .card-content-clamp) so
        # every card is the same, shorter height — this rough character-count
        # heuristic decides whether to show a "See more" button under it,
        # without needing JS to measure actual rendered overflow.
        memory.is_long_content = len(memory.content) > 90

        # The card thumbnail: the primary photo, falling back to the first
        # extra photo if there's no primary one (previously a memory added
        # with only "additional photos" and no primary photo showed no
        # thumbnail at all on the card, even though it had a photo). The
        # full gallery (for the enlarged view) is exposed as JSON so the
        # template doesn't need to duplicate hidden <img> tags for it.
        extra_list = list(memory.extra_photos.all())
        all_urls = ([memory.photo.url] if memory.photo else []) + [p.photo.url for p in extra_list]
        memory.photo_urls_json = json.dumps(all_urls)
        if memory.photo:
            memory.card_photo_url   = memory.photo.url
            memory.extra_photo_count = len(extra_list)
        elif extra_list:
            memory.card_photo_url   = extra_list[0].photo.url
            memory.extra_photo_count = len(extra_list) - 1
        else:
            memory.card_photo_url   = None
            memory.extra_photo_count = 0

    other_members = annotate_users(list(group.members.exclude(pk=user.pk)))
    all_members   = annotate_users(list(group.members.all()))
    admin_ids     = set(group.admins.values_list('pk', flat=True))
    for m in all_members:
        m.is_board_admin = m.pk in admin_ids

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

    is_owner   = group.owner == user
    is_admin   = group.is_admin(user)
    can_manage = is_owner or is_admin
    friend_groups = (FriendGroup.objects.filter(owner=user).annotate(member_count=Count('members'))
                      if can_manage else FriendGroup.objects.none())
    join_requests = (group.join_requests.select_related('requester') if can_manage
                      else BoardJoinRequest.objects.none())
    pending_invites = (group.pending_invites.filter(accepted=False).order_by('-created_at') if can_manage
                        else GroupInvite.objects.none())
    for jr in join_requests:
        jr.requester.initials     = get_initials(jr.requester)
        jr.requester.display_name = get_display_name(jr.requester)

    # For the "Add member" modal's quick-pick lists — friends not already
    # on this board, so a manager can invite with one click.
    owner_friends = []
    if can_manage:
        member_ids = set(group.members.values_list('pk', flat=True))
        owner_friends = annotate_users([
            f for f in Friendship.get_friends(user) if f.pk not in member_ids
        ])

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
        'current_sort':     sort,
        'filter_person':    filter_person,
        'filter_colour':    filter_colour,
        'filter_from':      filter_from,
        'filter_to':        filter_to,
        'search_query':     search_query,
        'filters_active':   bool(filter_person or filter_colour or filter_from or filter_to or search_query),
        'trashed_memories': trashed_memories,
        'other_members':    other_members,
        'all_members':      all_members,
        'note_font':        profile.note_font_css,
        'user_initials':    get_initials(user),
        'user_display':     get_display_name(user),
        'map_memories':     json.dumps(map_memories),
        'activity_log':     activity_log,
        'reaction_choices': REACTION_CHOICES,
        'colour_choices':   COLOUR_CHOICES,
        'is_owner':         is_owner,
        'is_admin':         is_admin,
        'can_manage':       can_manage,
        'can_delete_board': group.user_can_delete_board(user),
        'memory_delete_choices': MEMORY_DELETE_PERMISSION_CHOICES,
        'board_delete_choices':  BOARD_DELETE_PERMISSION_CHOICES,
        'privacy_choices':  PRIVACY_CHOICES,
        'friend_groups':    friend_groups,
        'owner_friends':    owner_friends,
        'join_requests':    join_requests,
        'pending_invites':  pending_invites,
    })


@login_required
def update_cover_view(request, pk):
    group = get_object_or_404(Group, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = GroupCoverForm(request.POST, request.FILES, instance=group)
        if form.is_valid():
            form.save()
            # A newly uploaded photo makes the old focal point meaningless —
            # reset to centered so it doesn't carry over onto a different image.
            group.cover_focal_y = 50
            group.save(update_fields=['cover_focal_y'])
            log_activity(group, request.user, 'cover_changed',
                         f'{get_display_name(request.user)} updated the board cover')
            return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=400)


@login_required
def update_cover_position_view(request, pk):
    group = get_object_or_404(Group, pk=pk, owner=request.user)
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=400)
    try:
        focal_y = int(json.loads(request.body).get('focal_y'))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid focal_y'}, status=400)
    focal_y = max(0, min(100, focal_y))
    group.cover_focal_y = focal_y
    group.save(update_fields=['cover_focal_y'])
    return JsonResponse({'ok': True, 'focal_y': focal_y})


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
@require_POST
def toggle_board_share_view(request, pk):
    """Turn the board's public, no-login read-only share link on or off.
    Toggling on when already on is a no-op (keeps the same link rather
    than rotating it, so a link someone already has doesn't silently
    break)."""
    group = get_board_for_manager(pk, request.user)
    enable = request.POST.get('enable', '1') == '1'
    if enable:
        if not group.share_token:
            group.share_token = uuid.uuid4()
            group.save(update_fields=['share_token'])
    else:
        group.share_token = None
        group.save(update_fields=['share_token'])
    share_url = request.build_absolute_uri(f'/shared/board/{group.share_token}/') if group.share_token else None
    return JsonResponse({'ok': True, 'enabled': bool(group.share_token), 'share_url': share_url})


def public_board_view(request, token):
    """Public, no-login read-only view of a board — reachable only with the
    share link (a valid share_token). No editing, commenting or reacting;
    just the memories, laid out simply."""
    group = get_object_or_404(Group, share_token=token)
    memories = (group.memories.filter(is_deleted=False)
                .select_related('creator').prefetch_related('tagged', 'extra_photos')
                .order_by('-is_pinned', '-created_at'))
    for m in memories:
        m.creator_display = get_display_name(m.creator)
        m.gallery_urls = m.all_photo_urls()
    return render(request, 'core/public_board.html', {'group': group, 'memories': memories})


@login_required
@require_POST
def invite_by_email_view(request, pk):
    """Unified "Add member" endpoint: takes a single query that can be a
    username or an email address (in this app usernames are just the
    account's email, truncated to 150 chars — see RegisterForm — so
    matching on both covers the same ground). A match on an existing
    account always goes through the pending-invite/accept flow, never an
    instant add; a query with no matching account falls back to emailing
    an invite, provided it's shaped like an email address.

    Note: this deliberately searches ALL accounts, not just the inviter's
    friends — narrowing username search to friends-only is a requested
    follow-up, not implemented yet.
    """
    group = get_board_for_manager(pk, request.user)
    query = request.POST.get('email', '').strip()
    if not query:
        return JsonResponse({'ok': False, 'error': 'Enter a username or email address.'}, status=400)

    existing = User.objects.filter(
        Q(email__iexact=query) | Q(username__iexact=query)
    ).exclude(pk=request.user.pk).first()

    if not existing:
        # Not a literal username/email match — try matching on the name
        # shown in the UI (what people actually type), same as lookup_user_view.
        parts = query.split()
        if len(parts) >= 2:
            existing = User.objects.filter(
                first_name__iexact=parts[0],
                last_name__iexact=' '.join(parts[1:]),
            ).exclude(pk=request.user.pk).first()

    if existing:
        email = existing.email
        if group.members.filter(pk=existing.pk).exists():
            return JsonResponse({'ok': False, 'error': 'That person is already a member of this board.'}, status=400)
        if GroupInvite.objects.filter(group=group, invited_user=existing, accepted=False).exists():
            return JsonResponse({'ok': False, 'error': 'An invite was already sent to that person.'}, status=400)
        # They already have an account — invite them in-app rather than
        # adding them directly; they accept or decline from Notifications.
        invite = GroupInvite.objects.create(
            group=group, invited_by=request.user, email=email, invited_user=existing)
        create_notification(
            existing, request.user, 'board_invite_pending',
            f'{get_display_name(request.user)} invited you to join "{group.name}"',
            group=group,
        )
        # Also offer to become friends, so they don't just end up in a
        # shared board as a stranger. Skip if already friends or a request
        # is already pending either way.
        already_related = (
            Friendship.are_friends(request.user, existing)
            or FriendRequest.objects.filter(from_user=request.user, to_user=existing).exists()
            or FriendRequest.objects.filter(from_user=existing, to_user=request.user).exists()
        )
        if not already_related:
            FriendRequest.objects.create(from_user=request.user, to_user=existing)
            create_notification(
                existing, request.user, 'friend_req',
                f'{get_display_name(request.user)} sent you a friend request',
            )
        return JsonResponse({'ok': True, 'invite_pk': invite.pk, 'email': email, 'message': f'Invite sent to {get_display_name(existing)} — they\'ll need to accept it.'})

    email = query.lower()
    try:
        django_forms.EmailField().clean(email)
    except django_forms.ValidationError:
        return JsonResponse({'ok': False, 'error': "No Rememory account found with that username. To invite someone new, enter their email address instead."}, status=404)

    if group.members.filter(email__iexact=email).exists():
        return JsonResponse({'ok': False, 'error': 'That person is already a member of this board.'}, status=400)
    if GroupInvite.objects.filter(group=group, email__iexact=email, accepted=False).exists():
        return JsonResponse({'ok': False, 'error': 'An invite was already sent to that address.'}, status=400)

    invite = GroupInvite.objects.create(group=group, invited_by=request.user, email=email)
    # They don't have an account yet — also record a friend invite so that,
    # like the standalone "invite a friend by email" flow, they're
    # auto-friended with the inviter the moment they register.
    friend_invite, friend_invite_created = FriendInvite.objects.get_or_create(
        from_user=request.user, email=email)
    sent, err = send_invite_email(request.user, email, group, invite.token)
    if sent:
        return JsonResponse({'ok': True, 'invite_pk': invite.pk, 'email': email, 'message': f'Invitation sent to {email}!'})
    else:
        invite.delete()
        if friend_invite_created:
            friend_invite.delete()
        return JsonResponse({'ok': False, 'error': f'Failed to send email: {err}'}, status=500)


@login_required
@require_POST
def invite_friend_group_view(request, pk, fg_pk):
    """Quick-pick from the Add Member modal: invite every member of one of
    the owner's friend groups in one click. Friend group members are
    always existing accounts (they're drawn from the owner's friends), so
    this always goes through the pending-invite/accept flow, same as a
    single-person match in invite_by_email_view — never an instant add."""
    group  = get_board_for_manager(pk, request.user)
    fgroup = get_object_or_404(FriendGroup, pk=fg_pk, owner=request.user)

    invited = []
    already = 0
    for member in fgroup.members.all():
        if group.members.filter(pk=member.pk).exists():
            already += 1
            continue
        if GroupInvite.objects.filter(group=group, invited_user=member, accepted=False).exists():
            already += 1
            continue
        invite = GroupInvite.objects.create(
            group=group, invited_by=request.user, email=member.email, invited_user=member)
        create_notification(
            member, request.user, 'board_invite_pending',
            f'{get_display_name(request.user)} invited you to join "{group.name}"',
            group=group,
        )
        invited.append({'pk': invite.pk, 'email': member.email})

    if invited:
        extra = f' ({already} already in/invited)' if already else ''
        message = f'Invited {len(invited)} member{"s" if len(invited) != 1 else ""} from "{fgroup.name}"{extra}.'
    else:
        message = f'Everyone in "{fgroup.name}" is already a board member or already invited.'
    return JsonResponse({'ok': True, 'invited': invited, 'message': message})


@login_required
@require_POST
def resend_invite_view(request, pk, invite_pk):
    group  = get_board_for_manager(pk, request.user)
    invite = get_object_or_404(GroupInvite, pk=invite_pk, group=group, accepted=False)
    if invite.invited_user:
        create_notification(
            invite.invited_user, request.user, 'board_invite_pending',
            f'{get_display_name(request.user)} invited you to join "{group.name}"',
            group=group,
        )
        return JsonResponse({'ok': True, 'message': f'Invite re-sent to {get_display_name(invite.invited_user)}.'})
    sent, err = send_invite_email(request.user, invite.email, group, invite.token)
    if sent:
        return JsonResponse({'ok': True, 'message': f'Invitation re-sent to {invite.email}!'})
    return JsonResponse({'ok': False, 'error': f'Failed to send email: {err}'}, status=500)


@login_required
@require_POST
def accept_board_invite_view(request, invite_pk):
    invite = get_object_or_404(GroupInvite, pk=invite_pk, invited_user=request.user, accepted=False)
    invite.accepted = True
    invite.save()
    invite.group.members.add(request.user)
    log_activity(invite.group, request.user, 'member_join',
                 f'{get_display_name(request.user)} joined the board')
    messages.success(request, f'You\'ve joined "{invite.group.name}"!')
    return redirect('group_detail', pk=invite.group.pk)


@login_required
@require_POST
def decline_board_invite_view(request, invite_pk):
    invite = get_object_or_404(GroupInvite, pk=invite_pk, invited_user=request.user, accepted=False)
    invite.delete()
    messages.info(request, "Invite declined.")
    return redirect('notifications')


@login_required
@require_POST
def cancel_invite_view(request, pk, invite_pk):
    group  = get_board_for_manager(pk, request.user)
    invite = get_object_or_404(GroupInvite, pk=invite_pk, group=group, accepted=False)
    email  = invite.email
    invite.delete()
    return JsonResponse({'ok': True, 'message': f'Invitation to {email} cancelled.'})


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
    group    = get_board_for_manager(pk, request.user)
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
    group    = get_board_for_manager(pk, request.user)
    join_req = get_object_or_404(BoardJoinRequest, pk=req_id, board=group)
    if request.method == 'POST':
        join_req.delete()
        messages.info(request, "Join request declined.")
    return redirect('group_detail', pk=pk)


@login_required
@require_POST
def make_admin_view(request, pk, user_id):
    """Only the board owner can appoint admins — admins themselves can't
    promote other members, to keep 'who granted this' unambiguous."""
    group  = get_object_or_404(Group, pk=pk, owner=request.user)
    target = get_object_or_404(User, pk=user_id)
    if not group.members.filter(pk=target.pk).exists():
        return JsonResponse({'ok': False, 'error': 'That person is not a member of this board.'}, status=400)
    if target == group.owner:
        return JsonResponse({'ok': False, 'error': "The owner doesn't need admin — they already manage everything."}, status=400)
    group.admins.add(target)
    create_notification(
        target, request.user, 'board_invite',
        f'{get_display_name(request.user)} made you an admin of "{group.name}"',
        group=group,
    )
    return JsonResponse({'ok': True, 'message': f'{get_display_name(target)} is now an admin.'})


@login_required
@require_POST
def remove_admin_view(request, pk, user_id):
    group  = get_object_or_404(Group, pk=pk, owner=request.user)
    target = get_object_or_404(User, pk=user_id)
    group.admins.remove(target)
    return JsonResponse({'ok': True, 'message': f'{get_display_name(target)} is no longer an admin.'})


# ── Friend Groups ─────────────────────────────────────────────────────────────

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
    return redirect('friends')


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
            for photo in form.cleaned_data.get('extra_photos', []):
                MemoryPhoto.objects.create(memory=memory, photo=photo)
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

    if request.method == 'GET':
        # Fetched via AJAX by openEditModal() and injected into the Edit
        # Memory modal — return just the form fragment, not a full page.
        if not memory.can_edit(request.user):
            return HttpResponseForbidden("You don't have permission to edit that memory.")
        tagged_ids = list(memory.tagged.values_list('pk', flat=True))
        return render(request, 'core/_edit_memory_fragment.html', {
            'memory':      memory,
            'group':       memory.group,
            'all_members': annotate_users(list(memory.group.members.all())),
            'tagged_ids':  tagged_ids,
            'extra_photos': memory.extra_photos.all(),
        })

    if not memory.can_edit(request.user):
        messages.error(request, "You don't have permission to edit that memory.")
        return redirect('group_detail', pk=memory.group.pk)

    form = EditMemoryForm(request.POST, request.FILES, instance=memory, group=memory.group)
    if form.is_valid():
        form.save()
        remove_ids = request.POST.getlist('remove_photo')
        if remove_ids:
            memory.extra_photos.filter(pk__in=remove_ids).delete()
        for photo in form.cleaned_data.get('extra_photos', []):
            MemoryPhoto.objects.create(memory=memory, photo=photo)
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
@require_POST
def bulk_delete_memories_view(request, pk):
    """Housekeeping: soft-delete several memories at once from the
    multi-select bar. Each one is still checked against can_delete()
    individually — selecting a memory you're not allowed to delete just
    skips it rather than failing the whole batch."""
    group = get_object_or_404(Group, pk=pk)
    if request.user not in group.members.all():
        return JsonResponse({'ok': False, 'error': 'Not a member of this board.'}, status=403)
    ids = request.POST.getlist('memory_ids')
    memories = group.memories.filter(pk__in=ids, is_deleted=False)
    deleted = 0
    for memory in memories:
        if memory.can_delete(request.user):
            memory.is_deleted = True
            memory.deleted_at = timezone.now()
            memory.save(update_fields=['is_deleted', 'deleted_at'])
            deleted += 1
    if deleted:
        log_activity(group, request.user, 'memory_delete',
                     f'{get_display_name(request.user)} deleted {deleted} memor{"y" if deleted == 1 else "ies"} at once')
    skipped = len(ids) - deleted
    message = f'Moved {deleted} memor{"y" if deleted == 1 else "ies"} to the recycle bin.'
    if skipped:
        message += f' ({skipped} skipped — no permission.)'
    return JsonResponse({'ok': True, 'deleted': deleted, 'message': message})


@login_required
def surprise_memory_view(request, pk):
    """'Surprise me' — jump to a random past memory on this board,
    ignoring whatever filters/sort are currently applied."""
    group = get_object_or_404(Group, pk=pk)
    if request.user not in group.members.all():
        return JsonResponse({'ok': False, 'error': 'Not a member of this board.'}, status=403)
    ids = list(group.memories.filter(is_deleted=False).values_list('pk', flat=True))
    if not ids:
        return JsonResponse({'ok': False, 'error': 'No memories on this board yet.'})
    return JsonResponse({'ok': True, 'pk': random.choice(ids)})


@login_required
def export_board_view(request, pk):
    """Housekeeping: download the whole board as a zip — a text summary of
    every memory (title, date, location, creator, tags, content) plus all
    of its photos, so people have an offline copy."""
    group = get_object_or_404(Group, pk=pk)
    if request.user not in group.members.all():
        messages.error(request, "You're not a member of that board.")
        return redirect('group_detail', pk=pk)

    memories = (group.memories.filter(is_deleted=False)
                .select_related('creator').prefetch_related('tagged', 'extra_photos')
                .order_by('created_at'))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        lines = [f'{group.name}', f'{"=" * len(group.name)}', '']
        for i, memory in enumerate(memories, start=1):
            lines.append(f'--- Memory {i} ---')
            if memory.title:
                lines.append(f'Title: {memory.title}')
            lines.append(f'By: {get_display_name(memory.creator)}')
            if memory.memory_date:
                lines.append(f'Date: {memory.memory_date}')
            if memory.location_name:
                lines.append(f'Location: {memory.location_name}')
            tagged = ', '.join(get_display_name(t) for t in memory.tagged.all())
            if tagged:
                lines.append(f'Tagged: {tagged}')
            lines.append('')
            lines.append(memory.content)
            lines.append('')
            for j, url in enumerate(memory.all_photo_urls(), start=1):
                path = url.split('?')[0]
                fs_path = path.replace(settings.MEDIA_URL, '', 1) if path.startswith(settings.MEDIA_URL) else None
                if fs_path:
                    abs_path = os.path.join(settings.MEDIA_ROOT, fs_path)
                    if os.path.exists(abs_path):
                        ext = os.path.splitext(abs_path)[1] or '.jpg'
                        arcname = f'memory-{i}-photo-{j}{ext}'
                        zf.write(abs_path, arcname)
                        lines.append(f'[photo: {arcname}]')
            lines.append('')
        zf.writestr('memories.txt', '\n'.join(lines))

    buf.seek(0)
    safe_name = ''.join(c for c in group.name if c.isalnum() or c in ' -_').strip() or 'board'
    response = HttpResponse(buf.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.zip"'
    return response


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


@login_required
@require_POST
def toggle_memory_share_view(request, pk):
    memory = get_object_or_404(Memory, pk=pk, is_deleted=False)
    if not memory.can_share(request.user):
        return JsonResponse({'ok': False, 'error': "You don't have permission to share this memory."}, status=403)
    enable = request.POST.get('enable', '1') == '1'
    if enable:
        if not memory.share_token:
            memory.share_token = uuid.uuid4()
            memory.save(update_fields=['share_token'])
    else:
        memory.share_token = None
        memory.save(update_fields=['share_token'])
    share_url = request.build_absolute_uri(f'/shared/memory/{memory.share_token}/') if memory.share_token else None
    return JsonResponse({'ok': True, 'enabled': bool(memory.share_token), 'share_url': share_url})


def public_memory_view(request, token):
    """Public, no-login read-only view of a single memory."""
    memory = get_object_or_404(Memory, share_token=token, is_deleted=False)
    gallery_urls = memory.all_photo_urls()
    tagged = list(memory.tagged.all())
    for t in tagged:
        t.display_name = get_display_name(t)
    return render(request, 'core/public_memory.html', {
        'memory': memory,
        'group': memory.group,
        'creator_display': get_display_name(memory.creator),
        'gallery_urls': gallery_urls,
        'tagged': tagged,
    })


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
                'can_edit':     True,
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
            'can_edit':   c.author == request.user,
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


@login_required
@require_POST
def edit_comment_view(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user)
    data    = json.loads(request.body)
    content = data.get('content', '').strip()
    if not content:
        return JsonResponse({'ok': False, 'error': 'Comment cannot be empty.'}, status=400)
    comment.content = content
    comment.save(update_fields=['content', 'updated_at'])
    return JsonResponse({'ok': True, 'comment': {'id': comment.pk, 'content': comment.content}})


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
    user          = request.user
    friends       = list(Friendship.get_friends(user))
    pending_in    = FriendRequest.objects.filter(to_user=user, accepted=False).select_related('from_user')
    pending_out   = FriendRequest.objects.filter(from_user=user, accepted=False).select_related('to_user')
    friend_groups = FriendGroup.objects.filter(owner=user).annotate(member_count=Count('members'))
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
        'friend_groups': friend_groups,
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
    })


@login_required
def send_friend_request_view(request):
    if request.method == 'POST':
        form = FriendRequestForm(request.POST, from_user=request.user)
        if form.is_valid():
            if form._resolved_user:
                FriendRequest.objects.get_or_create(
                    from_user=request.user, to_user=form._resolved_user)
                create_notification(
                    form._resolved_user, request.user, 'friend_req',
                    f'{get_display_name(request.user)} sent you a friend request',
                )
                messages.success(request, f"Friend request sent to {get_display_name(form._resolved_user)}!")
            else:
                email  = form.cleaned_data['query'].strip().lower()
                invite = FriendInvite.objects.create(from_user=request.user, email=email)
                sent, err = send_friend_invite_email(request.user, email, invite.token)
                if sent:
                    messages.success(request, f"{email} isn't on Rememory yet — we've emailed them an invite. You'll be friends automatically once they sign up.")
                else:
                    invite.delete()
                    messages.error(request, f"Failed to send email: {err}")
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
    shared_boards = (Group.objects.filter(members=user).filter(members=friend)
                      .annotate(memory_count=Count('memories', filter=Q(memories__is_deleted=False))))
    # Reachable either as an actual friend, or as a fellow board member —
    # this is also the view opened by clicking a name in a board's Members
    # list, where the two people may not be friends yet.
    if not Friendship.are_friends(user, friend) and not shared_boards.exists():
        messages.error(request, "You don't share a board or friendship with that person.")
        return redirect('friends')
    mutual_ids     = set(Friendship.get_friends(user).values_list('pk', flat=True)) & \
                     set(Friendship.get_friends(friend).values_list('pk', flat=True))
    mutual_friends = annotate_users(list(User.objects.filter(pk__in=mutual_ids)))

    u1, u2 = (user, friend) if user.id < friend.id else (friend, user)
    friendship   = Friendship.objects.filter(user1=u1, user2=u2).first()
    friends_since = friendship.created_at if friendship else None

    friend_profile  = friend.profile
    show_info       = friend_profile.info_visibility == 'friends' and friend_profile.has_info

    return render(request, 'core/friend_profile.html', {
        'friend':          friend,
        'friend_initials': get_initials(friend),
        'friend_display':  get_display_name(friend),
        'shared_boards':   shared_boards,
        'mutual_friends':  mutual_friends,
        'friends_since':   friends_since,
        'friend_profile':  friend_profile,
        'show_info':       show_info,
        'friend_stats':    get_user_stats(friend),
        'user_initials':   get_initials(user),
        'user_display':    get_display_name(user),
    })


@login_required
def my_profile_view(request):
    user    = request.user
    profile = user.profile
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect('my_profile')
    else:
        form = ProfileForm(instance=profile)

    return render(request, 'core/my_profile.html', {
        'form':          form,
        'profile':       profile,
        'stats':         get_user_stats(user),
        'user_initials': get_initials(user),
        'user_display':  get_display_name(user),
        'font_choices':  FONT_CHOICES,
        'current_font':  profile.note_font,
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
        "name": "Rememory",
        "short_name": "Rememory",
        "description": "For things worth remembering",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#EAE2CD",
        "theme_color": "#8C6A2F",
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
