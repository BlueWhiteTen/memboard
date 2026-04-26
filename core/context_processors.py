from .models import Group, FriendRequest


def sidebar_context(request):
    if not request.user.is_authenticated:
        return {}
    from .views import get_initials, get_display_name
    user          = request.user
    pending_count = FriendRequest.objects.filter(to_user=user, accepted=False).count()
    user_groups   = Group.objects.filter(members=user).order_by('-created_at')
    return {
        'user_groups':             user_groups,
        'pending_requests_count':  pending_count,
        'user_initials':           get_initials(user),
        'user_display':            get_display_name(user),
    }
