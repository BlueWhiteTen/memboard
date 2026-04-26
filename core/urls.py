from django.urls import path
from . import views

urlpatterns = [
    path('',          views.home_view,     name='home'),
    path('register/', views.register_view, name='register'),
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),

    path('groups/new/',                    views.create_group_view,   name='create_group'),
    path('groups/<int:pk>/',               views.group_detail_view,   name='group_detail'),
    path('groups/<int:pk>/invite/',        views.invite_member_view,  name='invite_member'),
    path('groups/<int:pk>/invite-email/',  views.invite_by_email_view, name='invite_by_email'),
    path('groups/<int:pk>/delete/',        views.delete_group_view,   name='delete_group'),

    path('groups/<int:pk>/memory/add/', views.add_memory_view,    name='add_memory'),
    path('memory/<int:pk>/edit/',       views.edit_memory_view,   name='edit_memory'),
    path('memory/<int:pk>/delete/',     views.delete_memory_view, name='delete_memory'),

    path('friends/',                           views.friends_view,                name='friends'),
    path('friends/request/',                   views.send_friend_request_view,    name='send_friend_request'),
    path('friends/accept/<int:request_id>/',   views.accept_friend_request_view,  name='accept_friend_request'),
    path('friends/decline/<int:request_id>/',  views.decline_friend_request_view, name='decline_friend_request'),
    path('friends/remove/<int:user_id>/',      views.remove_friend_view,          name='remove_friend'),

    path('api/set-font/',    views.set_font_view,    name='set_font'),
    path('api/lookup-user/', views.lookup_user_view, name='lookup_user'),
]
