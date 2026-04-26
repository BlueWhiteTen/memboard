from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse

from .models import Group, Memory, Friendship, FriendRequest, UserProfile, GroupInvite, FONT_CHOICES
from .forms import (
    RegisterForm, EmailAuthenticationForm, GroupForm,
    MemoryForm, EditMemoryForm, InviteMemberForm, FriendRequestForm,
)
from .email_utils import send_invite_email


def get_initials(user):
    """Return up to 2 initials from first+last name, fallback to email."""
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


# ── Auth ──────────────────────────────────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    invite_token = request.GET.get('invite') or request.POST.get('invite_token')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        UserProfile.objects.get_or_create(user=user)
        # auto-add via invite token
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
        # auto-add any other pending invites for this email
        if user.email:
            for inv in GroupInvite.objects.filter(email__iexact=user.email, accepted=False):
                inv.group.members.add(user)
                inv.accepted = True
                inv.save()
        login(request, user)
        messages.success(request, f"Welcome to Memboard, {user.first_name}!")
        return redirect('home')
    return render(request, 'core/register.html', {
        'form': form, 'invite_token': invite_token})


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
    # annotate friends with initials/display name
    for f in friends:
        f.initials    = get_initials(f)
        f.display_name = get_display_name(f)
    return render(request, 'core/home.html', {
        'user_groups':      user_groups,
        'friends':          friends,
        'pending_requests': pending_in,
        'total_memories':   total_memories,
        'user_initials':    get_initials(user),
        'user_display':     get_display_name(user),
    })


# ── Groups ────────────────────────────────────────────────────────────────────

@login_required
def create_group_view(request):
    user    = request.user
    friends = Friendship.get_friends(user)
    for f in friends:
        f.initials     = get_initials(f)
        f.display_name = get_display_name(f)

    if request.method == 'POST':
        form = GroupForm(request.POST)
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

    memories = (group.memories
                .select_related('creator')
                .prefetch_related('tagged'))
    user = request.user
    for memory in memories:
        memory.user_can_edit    = memory.can_edit(user)
        memory.creator_initials = get_initials(memory.creator)
        memory.creator_display  = get_display_name(memory.creator)
        for t in memory.tagged.all():
            t.initials     = get_initials(t)
            t.display_name = get_display_name(t)

    other_members = list(group.members.exclude(pk=user.pk))
    for m in other_members:
        m.initials     = get_initials(m)
        m.display_name = get_display_name(m)

    all_members = list(group.members.all())
    for m in all_members:
        m.initials     = get_initials(m)
        m.display_name = get_display_name(m)

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
    })


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
            group.members.add(form._resolved_user)
            messages.success(request, f"{get_display_name(form._resolved_user)} added!")
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
            messages.success(request, "Memory updated!")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    return redirect('group_detail', pk=memory.group.pk)


@login_required
def delete_memory_view(request, pk):
    memory = get_object_or_404(Memory, pk=pk, creator=request.user)
    group_pk = memory.group.pk
    if request.method == 'POST':
        memory.delete()
        messages.success(request, "Memory removed.")
    return redirect('group_detail', pk=group_pk)


# ── Friends ───────────────────────────────────────────────────────────────────

@login_required
def friends_view(request):
    user        = request.user
    friends     = Friendship.get_friends(user)
    pending_in  = FriendRequest.objects.filter(to_user=user, accepted=False).select_related('from_user')
    pending_out = FriendRequest.objects.filter(from_user=user, accepted=False).select_related('to_user')
    for f in friends:
        f.initials     = get_initials(f)
        f.display_name = get_display_name(f)
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
