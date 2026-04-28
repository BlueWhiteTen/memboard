from .models import Notification


def sidebar_context(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return {'unread_notifs': unread}
    return {'unread_notifs': 0}
