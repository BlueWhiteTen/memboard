from django.contrib import admin
from .models import Group, Memory, Friendship, FriendRequest, UserProfile, GroupInvite, Reaction, Comment, Notification, ActivityLog

admin.site.register(Group)
admin.site.register(Memory)
admin.site.register(Friendship)
admin.site.register(FriendRequest)
admin.site.register(UserProfile)
admin.site.register(GroupInvite)
admin.site.register(Reaction)
admin.site.register(Comment)
admin.site.register(Notification)
admin.site.register(ActivityLog)
