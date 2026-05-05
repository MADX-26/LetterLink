from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    path('create/', views.create_room, name='create_room'),
    path('join/', views.join_room, name='join_room'),

    path('lobby/<str:room_name>/', views.lobby_view, name='lobby'),
    path('play/<str:room_name>/', views.game_view, name='play'),

    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('history/', views.history_view, name='history'),
]