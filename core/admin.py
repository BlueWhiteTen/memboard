from django.contrib import admin
from .models import Group, Memory, Friendship, FriendRequest, UserProfile, GroupInvite

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'note_font')

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'privacy', 'created_at')
    filter_horizontal = ('members',)

@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'creator', 'group', 'edit_permission', 'created_at')
    filter_horizontal = ('tagged',)

@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ('user1', 'user2', 'created_at')

@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ('from_user', 'to_user', 'accepted', 'created_at')

@admin.register(GroupInvite)
class GroupInviteAdmin(admin.ModelAdmin):
    list_display = ('email', 'group', 'invited_by', 'accepted', 'created_at')
