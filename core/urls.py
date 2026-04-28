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
    path('groups/<int:pk>/delete/',       views.delete_group_view,    name='delete_group'),
    path('groups/<int:pk>/cover/',        views.update_cover_view,    name='update_cover'),

    # Memories
    path('groups/<int:pk>/memory/add/', views.add_memory_view,    name='add_memory'),
    path('memory/<int:pk>/edit/',       views.edit_memory_view,   name='edit_memory'),
    path('memory/<int:pk>/delete/',     views.delete_memory_view, name='delete_memory'),
    path('memory/<int:pk>/pin/',        views.pin_memory_view,    name='pin_memory'),

    # Reactions & Comments
    path('memory/<int:pk>/react/',          views.react_memory_view,  name='react_memory'),
    path('memory/<int:pk>/comments/',       views.comments_view,      name='memory_comments'),
    path('comment/<int:pk>/delete/',        views.delete_comment_view, name='delete_comment'),

    # Annual Recap
    path('recap/',             views.annual_recap_view, name='annual_recap'),
    path('recap/<int:year>/',  views.annual_recap_view, name='annual_recap_year'),

    # Friends
    path('friends/',                          views.friends_view,                name='friends'),
    path('friends/request/',                  views.send_friend_request_view,    name='send_friend_request'),
    path('friends/accept/<int:request_id>/',  views.accept_friend_request_view,  name='accept_friend_request'),
    path('friends/decline/<int:request_id>/', views.decline_friend_request_view, name='decline_friend_request'),
    path('friends/remove/<int:user_id>/',     views.remove_friend_view,          name='remove_friend'),

    # API / settings
    path('api/set-font/',           views.set_font_view,              name='set_font'),
    path('api/lookup-user/',        views.lookup_user_view,           name='lookup_user'),
    path('api/push-subscribe/',     views.save_push_subscription_view, name='push_subscribe'),

    # PWA
    path('sw.js',       views.sw_view,       name='sw'),
    path('manifest.json', views.manifest_view, name='manifest'),
]
