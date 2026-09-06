from django.urls import path
from . import views

urlpatterns = [
    path('',          views.home_view,     name='home'),
    path('register/', views.register_view, name='register'),
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),

    # Search
    path('search/', views.search_view, name='search'),

    # Notifications
    path('notifications/',               views.notifications_view,    name='notifications'),
    path('notifications/<int:pk>/read/', views.mark_notif_read_view,  name='mark_notif_read'),

    # Groups
    path('groups/new/',                   views.create_group_view,    name='create_group'),
    path('groups/<int:pk>/',              views.group_detail_view,    name='group_detail'),
    path('groups/<int:pk>/invite/',       views.invite_member_view,   name='invite_member'),
    path('groups/<int:pk>/invite-email/', views.invite_by_email_view, name='invite_by_email'),
    path('groups/<int:pk>/invites/<int:invite_pk>/resend/', views.resend_invite_view, name='resend_invite'),
    path('groups/<int:pk>/invites/<int:invite_pk>/cancel/', views.cancel_invite_view, name='cancel_invite'),
    path('board-invites/<int:invite_pk>/accept/', views.accept_board_invite_view, name='accept_board_invite'),
    path('board-invites/<int:invite_pk>/decline/', views.decline_board_invite_view, name='decline_board_invite'),
    path('groups/<int:pk>/delete/',       views.delete_group_view,    name='delete_group'),
    path('groups/<int:pk>/cover/',        views.update_cover_view,    name='update_cover'),
    path('groups/<int:pk>/leave/',        views.leave_board_view,     name='leave_board'),
    path('groups/<int:pk>/settings/',     views.update_board_settings_view, name='update_board_settings'),
    path('groups/<int:pk>/request-join/', views.request_join_board_view, name='request_join_board'),
    path('groups/<int:pk>/join-requests/<int:req_id>/approve/', views.approve_join_request_view, name='approve_join_request'),
    path('groups/<int:pk>/join-requests/<int:req_id>/decline/', views.decline_join_request_view, name='decline_join_request'),

    # Friend Groups
    path('friend-groups/new/',        views.create_friend_group_view,  name='create_friend_group'),
    path('friend-groups/<int:pk>/',   views.friend_group_detail_view,  name='friend_group_detail'),
    path('friend-groups/<int:pk>/delete/', views.delete_friend_group_view, name='delete_friend_group'),

    # Memories
    path('groups/<int:pk>/memory/add/', views.add_memory_view,    name='add_memory'),
    path('memory/<int:pk>/edit/',       views.edit_memory_view,   name='edit_memory'),
    path('memory/<int:pk>/delete/',     views.delete_memory_view, name='delete_memory'),
    path('memory/<int:pk>/restore/',    views.restore_memory_view, name='restore_memory'),
    path('memory/<int:pk>/pin/',        views.pin_memory_view,    name='pin_memory'),

    # Reactions & Comments
    path('memory/<int:pk>/react/',          views.react_memory_view,  name='react_memory'),
    path('memory/<int:pk>/comments/',       views.comments_view,      name='memory_comments'),
    path('comment/<int:pk>/delete/',        views.delete_comment_view, name='delete_comment'),

    # Annual Recap
    path('recap/',             views.annual_recap_view, name='annual_recap'),
    path('recap/<int:year>/',  views.annual_recap_view, name='annual_recap_year'),

    # On This Day
    path('on-this-day/', views.on_this_day_view, name='on_this_day'),

    # Friends
    path('friends/',                          views.friends_view,                name='friends'),
    path('friends/request/',                  views.send_friend_request_view,    name='send_friend_request'),
    path('friends/accept/<int:request_id>/',  views.accept_friend_request_view,  name='accept_friend_request'),
    path('friends/decline/<int:request_id>/', views.decline_friend_request_view, name='decline_friend_request'),
    path('friends/remove/<int:user_id>/',     views.remove_friend_view,          name='remove_friend'),
    path('friends/<int:user_id>/',            views.friend_profile_view,         name='friend_profile'),

    # My Profile
    path('profile/', views.my_profile_view, name='my_profile'),

    # API / settings
    path('api/set-font/',           views.set_font_view,              name='set_font'),
    path('api/set-theme/',          views.set_theme_view,             name='set_theme'),
    path('api/lookup-user/',        views.lookup_user_view,           name='lookup_user'),
    path('api/push-subscribe/',     views.save_push_subscription_view, name='push_subscribe'),

    # PWA
    path('sw.js',       views.sw_view,       name='sw'),
    path('manifest.json', views.manifest_view, name='manifest'),
]
