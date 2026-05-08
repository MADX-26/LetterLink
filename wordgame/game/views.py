from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from .models import Match
import random
import string


# ==========================
# ROOM CODE GENERATOR
# ==========================

def generate_room_code(length=6):

    return ''.join(

        random.choices(
            string.ascii_uppercase + string.digits,
            k=length
        )
    )


# ==========================
# HOME PAGE
# ==========================

def home(request):

    if not request.user.is_authenticated:
        return redirect('login')

    return render(
        request,
        "game/home.html"
    )


# ==========================
# CREATE ROOM
# ==========================

def create_room(request):

    code = generate_room_code()

    return redirect(f"/lobby/{code}/")


# ==========================
# JOIN ROOM
# ==========================

def join_room(request):

    if request.method == "POST":

        code = request.POST.get("room_code")

        return redirect(f"/lobby/{code}/")

    return render(
        request,
        "game/join.html"
    )


# ==========================
# LOBBY
# ==========================

def lobby_view(request, room_name):

    if not request.user.is_authenticated:
        return redirect('login')

    return render(
        request,
        "game/lobby.html",
        {"room_name": room_name}
    )


# ==========================
# GAME PAGE
# ==========================

def game_view(request, room_name):

    if not request.user.is_authenticated:
        return redirect('login')

    return render(
        request,
        "game/index.html",
        {"room_name": room_name}
    )


# ==========================
# AUTH
# ==========================

def register_view(request):

    if request.method == "POST":

        username = request.POST['username']
        password = request.POST['password']

        User.objects.create_user(
            username=username,
            password=password
        )

        return redirect('login')

    return render(
        request,
        "game/register.html"
    )


def login_view(request):

    if request.method == "POST":

        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user:

            login(request, user)
            return redirect('home')

    return render(
        request,
        "game/login.html"
    )


def logout_view(request):

    logout(request)

    return redirect('login')

from django.db.models import Q, F

def leaderboard_view(request):
    if not request.user.is_authenticated:
        return redirect('login')

    users = User.objects.all()
    leaderboard = []

    for user in users:
        # Calculate wins: check if the winner string starts with the user's name
        wins = Match.objects.filter(
            Q(winner__startswith=f"{user.username} Wins")
        ).count()
        
        if wins > 0 or Match.objects.filter(Q(player1=user) | Q(player2=user)).exists():
            leaderboard.append({
                'username': user.username,
                'wins': wins
            })

    # Sort by wins descending
    leaderboard = sorted(leaderboard, key=lambda x: x['wins'], reverse=True)

    return render(
        request,
        "game/leaderboard.html",
        {"leaderboard": leaderboard}
    )
