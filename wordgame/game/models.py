from django.db import models
from django.contrib.auth.models import User


class Match(models.Model):

    player1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="player1_matches"
    )

    player2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="player2_matches"
    )

    score1 = models.IntegerField()
    score2 = models.IntegerField()

    winner = models.CharField(max_length=50)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):

        return f"{self.player1} vs {self.player2} - {self.winner}"