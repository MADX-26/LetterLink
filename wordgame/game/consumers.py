import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import Match
from django.contrib.auth.models import User
from asgiref.sync import sync_to_async   # 🔥 IMPORTANT

rooms = {}


class GameConsumer(AsyncWebsocketConsumer):

    async def connect(self):

        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f"game_{self.room_name}"

        self.username = self.scope["user"].username

        if self.room_name not in rooms:
            rooms[self.room_name] = {
                "players": [],
                "turn": 1,
                "board": [[None for _ in range(5)] for _ in range(5)],
                "scores": {1: 0, 2: 0},
                "used_words": set(),
                "processing": False
            }

        room = rooms[self.room_name]

        if len(room["players"]) >= 2:
            await self.close()
            return

        self.player_number = len(room["players"]) + 1

        room["players"].append({
            "channel": self.channel_name,
            "player": self.player_number,
            "username": self.username
        })

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        await self.send(json.dumps({
            "type": "player_assignment",
            "player": self.player_number
        }))

        if len(room["players"]) == 2:
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "start_game"}
            )

    async def start_game(self, event):
        await self.send(json.dumps({"type": "start_game"}))

    async def disconnect(self, close_code):

        if self.room_name in rooms:
            room = rooms[self.room_name]

            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "player_left"}
            )

            room["players"] = [
                p for p in room["players"]
                if p["channel"] != self.channel_name
            ]

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def player_left(self, event):
        await self.send(json.dumps({"type": "player_left"}))

    # ==========================
    # MAIN GAME LOGIC
    # ==========================

    async def receive(self, text_data):

        data = json.loads(text_data)
        room = rooms[self.room_name]

        if room["processing"]:
            return

        room["processing"] = True

        try:

            if data.get("type") == "restart":
                await self.restart_game()
                return

            player = data["player"]
            row = data["row"]
            col = data["col"]
            letter = data["letter"]

            if player != room["turn"]:
                return

            if room["board"][row][col] is not None:
                return

            # PLACE LETTER
            room["board"][row][col] = letter

            # CHECK WORDS
            new_words = self.check_words(room)

            points = sum(len(w) for w in new_words)
            room["scores"][player] += points

            # SWITCH TURN
            room["turn"] = 2 if player == 1 else 1

            # SEND FULL UPDATE
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "game_update",
                    "board": room["board"],
                    "turn": room["turn"],
                    "scores": room["scores"],
                    "words": new_words
                }
            )

            # ==========================
            # GAME END
            # ==========================

            if self.is_board_full(room["board"]):

                winner = self.get_winner(room["scores"])

                players = room["players"]

                # 🔥 FIX: async-safe DB call
                if len(players) == 2:
                    await self.save_match(players, room, winner)

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "game_end",
                        "scores": room["scores"],
                        "winner": winner
                    }
                )

        finally:
            room["processing"] = False

    # ==========================
    # 🔥 FIX FUNCTION (IMPORTANT)
    # ==========================

    @sync_to_async
    def save_match(self, players, room, winner):

        user1 = User.objects.get(username=players[0]["username"])
        user2 = User.objects.get(username=players[1]["username"])

        Match.objects.create(
            player1=user1,
            player2=user2,
            score1=room["scores"][1],
            score2=room["scores"][2],
            winner=winner
        )

    # ==========================
    # SEND EVENTS
    # ==========================

    async def game_update(self, event):
        await self.send(json.dumps({
            "type": "update",
            "board": event["board"],
            "turn": event["turn"],
            "scores": event["scores"],
            "words": event["words"]
        }))

    async def game_end(self, event):
        await self.send(json.dumps({
            "type": "game_end",
            "scores": event["scores"],
            "winner": event["winner"]
        }))

    async def restart_game(self):

        room = rooms[self.room_name]

        room["board"] = [[None for _ in range(5)] for _ in range(5)]
        room["scores"] = {1: 0, 2: 0}
        room["used_words"] = set()
        room["turn"] = 1

        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "game_reset"}
        )

    async def game_reset(self, event):
        await self.send(json.dumps({"type": "reset"}))

    # ==========================
    # WORD LOGIC
    # ==========================

    def check_words(self, room):

        board = room["board"]
        used = room["used_words"]

        dictionary = [
            "CAT","DOG","ANT","NOTE","APPLE",
            "BALL","TREE","FISH","BOOK","GAME",
            "CODE","WORD","GRID","HOME","CAR",
            "CARD","CARDS","NOTES"
        ]

        found = []

        for row in board:
            line = "".join([c if c else "" for c in row])
            found += self.find_words(line, dictionary, used)

        for col in range(5):
            line = "".join([
                board[r][col] if board[r][col] else ""
                for r in range(5)
            ])
            found += self.find_words(line, dictionary, used)

        return found

    def find_words(self, line, dictionary, used):

        found = []

        for i in range(len(line)):
            for j in range(i+3, len(line)+1):
                word = line[i:j]
                if word in dictionary and word not in used:
                    used.add(word)
                    found.append(word)

        return found

    def is_board_full(self, board):
        return all(all(cell is not None for cell in row) for row in board)

    def get_winner(self, scores):
        if scores[1] > scores[2]:
            return "Player 1 Wins!"
        elif scores[2] > scores[1]:
            return "Player 2 Wins!"
        else:
            return "Draw!"