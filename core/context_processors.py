from django.db.models import Max
from django.db.models.functions import Coalesce
from .models import Notification, Group, FriendRequest, UserProfile, LANGUAGE_CHOICES


def sidebar_context(request):
    # Native-name language list for the switcher in base.html and the
    # standalone auth pages — deliberately not the i18n context processor's
    # own LANGUAGES (that translates each language's *name*, e.g. showing
    # "Greek" instead of "Ελληνικά" while browsing in English).
    language_choices = LANGUAGE_CHOICES
    if request.user.is_authenticated:
        unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
        # Ordered by most recent activity (latest logged change on the
        # board, e.g. a new memory or comment), not by when the board was
        # created — falls back to the board's creation date for a brand
        # new board with no activity logged yet.
        all_boards = Group.objects.filter(members=request.user)
        sidebar_groups_count = all_boards.count()
        sidebar_groups = (all_boards
                           .annotate(last_activity=Coalesce(Max('activity_logs__created_at'), 'created_at'))
                           .order_by('-last_activity')[:10])
        pending_requests = FriendRequest.objects.filter(to_user=request.user, accepted=False)
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return {
            'unread_notifs': unread,
            'sidebar_groups': sidebar_groups,
            'sidebar_groups_count': sidebar_groups_count,
            'pending_requests': pending_requests,
            'user_theme': profile.theme,
            'language_choices': language_choices,
        }
    return {
        'unread_notifs': 0,
        'sidebar_groups': [],
        'sidebar_groups_count': 0,
        'pending_requests': [],
        'user_theme': 'light',
        'language_choices': language_choices,
    }
