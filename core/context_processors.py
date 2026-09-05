from .models import Notification, Group, FriendRequest, UserProfile


def sidebar_context(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
        sidebar_groups = Group.objects.filter(members=request.user).order_by('-created_at')[:10]
        pending_requests = FriendRequest.objects.filter(to_user=request.user, accepted=False)
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return {
            'unread_notifs': unread,
            'sidebar_groups': sidebar_groups,
            'pending_requests': pending_requests,
            'user_theme': profile.theme,
        }
    return {
        'unread_notifs': 0,
        'sidebar_groups': [],
        'pending_requests': [],
        'user_theme': 'system',
    }
