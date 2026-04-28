from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
import json

from .models import (
    Group, Memory, Friendship, FriendRequest, UserProfile,
    GroupInvite, Reaction, Comment, Notification, ActivityLog,
    FONT_CHOICES, REACTION_CHOICES,
)
from .forms import (
    RegisterForm, EmailAuthenticationForm, GroupForm, GroupCoverForm,
    MemoryForm, EditMemoryForm, InviteMemberForm, FriendRequestForm,
)
from .email_utils import send_invite_email


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


# ── Auth ──────────────────────────────────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    invite_token = request.GET.get('invite') or request.POST.get('invite_token')
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


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
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
                      .annotate(memory_count=Count('memories'))
                      .order_by('-created_at'))
    friends        = Friendship.get_friends(user)
    pending_in     = FriendRequest.objects.filter(to_user=user, accepted=False)
    total_memories = Memory.objects.filter(group__members=user).count()
    unread_notifs  = Notification.objects.filter(recipient=user, is_read=False).count()
    annotate_users(friends)
    return render(request, 'core/home.html', {
        'user_groups':      user_groups,
        'friends':          friends,
        'pending_requests': pending_in,
        'total_memories':   total_memories,
        'unread_notifs':    unread_notifs,
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
            group__members=user
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
    user    = request.user
    friends = annotate_users(list(Friendship.get_friends(user)))
    if request.method == 'POST':
        form = GroupForm(request.POST, request.FILES)
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
        form = GroupForm()
    return render(request, 'core/create_group.html', {
        'form': form, 'friends': friends,
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
                .select_related('creator')
                .prefetch_related('tagged', 'reactions', 'comments'))

    for memory in memories:
        memory.user_can_edit    = memory.can_edit(user)
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

    return render(request, 'core/group_detail.html', {
        'group':           group,
        'memories':        memories,
        'other_members':   other_members,
        'all_members':     all_members,
        'note_font':       profile.note_font_css,
        'font_choices':    FONT_CHOICES,
        'current_font':    profile.note_font,
        'user_initials':   get_initials(user),
        'user_display':    get_display_name(user),
        'map_memories':    json.dumps(map_memories),
        'activity_log':    activity_log,
        'reaction_choices': REACTION_CHOICES,
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
    group = get_object_or_404(Group, pk=pk, owner=request.user)
    if request.method == 'POST':
        name = group.name
        group.delete()
        messages.success(request, f'Board "{name}" deleted.')
    return redirect('home')


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
    memory = get_object_or_404(Memory, pk=pk)
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
    memory   = get_object_or_404(Memory, pk=pk, creator=request.user)
    group_pk = memory.group.pk
    if request.method == 'POST':
        log_activity(memory.group, request.user, 'memory_delete',
                     f'{get_display_name(request.user)} deleted a memory: {memory.title or memory.content[:40]}')
        memory.delete()
        messages.success(request, "Memory removed.")
    return redirect('group_detail', pk=group_pk)


@login_required
@require_POST
def pin_memory_view(request, pk):
    memory = get_object_or_404(Memory, pk=pk)
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
    memory = get_object_or_404(Memory, pk=pk)
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
    memory = get_object_or_404(Memory, pk=pk)
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


# ── Friends ───────────────────────────────────────────────────────────────────

@login_required
def friends_view(request):
    user        = request.user
    friends     = Friendship.get_friends(user)
    pending_in  = FriendRequest.objects.filter(to_user=user, accepted=False).select_related('from_user')
    pending_out = FriendRequest.objects.filter(from_user=user, accepted=False).select_related('to_user')
    annotate_users(friends)
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
