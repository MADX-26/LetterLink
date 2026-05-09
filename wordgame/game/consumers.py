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
                "processing": False,
                "usernames": {"1": None, "2": None}
            }

        room = rooms[self.room_name]

        # Check if this user is already in the room (reconnection/transition)
        self.player_number = None
        for num_str, name in room["usernames"].items():
            if name == self.username:
                self.player_number = int(num_str)
                break
        
        if self.player_number is None:
            # Assign a new slot if available
            if room["usernames"]["1"] is None:
                self.player_number = 1
            elif room["usernames"]["2"] is None:
                self.player_number = 2
            else:
                # Room full with 2 other people
                await self.close()
                return
            room["usernames"][str(self.player_number)] = self.username

        print(f"DEBUG: Player {self.username} assigned number {self.player_number}")
        print(f"DEBUG: Current room usernames: {room['usernames']}")

        # Track active channel
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
            "player": self.player_number,
            "username": self.username,
            "usernames": room["usernames"]
        }))

        if len(room["players"]) == 2:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "start_game",
                    "usernames": room["usernames"]
                }
            )

    async def start_game(self, event):
        await self.send(json.dumps({
            "type": "start_game",
            "usernames": event["usernames"]
        }))

    async def disconnect(self, close_code):

        if self.room_name in rooms:
            room = rooms[self.room_name]

            if len(room["players"]) == 2:
                other_player = [p for p in room["players"] if p["channel"] != self.channel_name][0]
                winner_username = other_player["username"]
                
                # Check if game has actually started (at least one letter placed)
                game_started = any(any(cell is not None for cell in row) for row in room["board"])

                if game_started and not self.is_board_full(room["board"]):
                    # Award win to the remaining player
                    await self.save_match_disconnect(
                        room["usernames"].get("1") or room["usernames"].get(1), 
                        room["usernames"].get("2") or room["usernames"].get(2), 
                        winner_username,
                        room["scores"][1],
                        room["scores"][2]
                    )

                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "player_left",
                            "winner": winner_username
                        }
                    )
                else:
                    # Notify player left without awarding a win (lobby or early exit)
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "player_left",
                            "winner": None
                        }
                    )

            room["players"] = [
                p for p in room["players"]
                if p["channel"] != self.channel_name
            ]
            
            # Clean up room if empty
            if len(room["players"]) == 0:
                del rooms[self.room_name]

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    @sync_to_async
    def save_match_disconnect(self, player1_username, player2_username, winner_username, score1, score2):
        try:
            user1 = User.objects.get(username=player1_username)
            user2 = User.objects.get(username=player2_username)
            
            winner_display = f"{winner_username} Wins! (Opponent Left)"
            
            Match.objects.create(
                player1=user1,
                player2=user2,
                score1=score1,
                score2=score2,
                winner=winner_display
            )
        except Exception as e:
            print(f"Error saving match on disconnect: {e}")

    async def player_left(self, event):
        await self.send(json.dumps({
            "type": "player_left",
            "winner": event.get("winner")
        }))

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

                scores = room["scores"]
                user1 = room["players"][0]["username"]
                user2 = room["players"][1]["username"]
                
                if scores[1] > scores[2]:
                    winner = f"{user1} Wins!"
                elif scores[2] > scores[1]:
                    winner = f"{user2} Wins!"
                else:
                    winner = "Draw!"

                players = room["players"]

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
        room = rooms.get(self.room_name, {})
        await self.send(json.dumps({
            "type": "update",
            "board": event["board"],
            "turn": event["turn"],
            "scores": event["scores"],
            "words": event["words"],
            "usernames": room.get("usernames", {"1": "Player 1", "2": "Player 2"})
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
            # 2 LETTER WORDS
            "AM","AN","AS","AT","AX","BE","BY","DO","GO","HE",
            "HI","IF","IN","IS","IT","ME","MY","NO","OF","ON",
            "OR","OX","PA","SO","TO","UP","US","WE","YE","YO",

            # 3 LETTER WORDS
            "ACE","ACT","ADD","AGE","AID","AIM","AIR","ALL","AND","ANT",
            "ANY","APE","APP","ARC","ARM","ART","ASH","ASK","AWE","AXE",
            "BAD","BAG","BAR","BAT","BAY","BED","BEE","BET","BID","BIG",
            "BIN","BIT","BOB","BOG","BOX","BOY","BUN","BUS","BUT","CAB",
            "CAN","CAP","CAR","CAT","CUP","CUT","DAD","DAM","DAY","DEN",
            "DID","DIG","DIM","DIN","DIP","DOG","DOT","DRY","DUE","EAR",
            "EAT","EGG","END","ERA","EYE","FAN","FAR","FAT","FAX","FED",
            "FEW","FIG","FIN","FIT","FIX","FLY","FOG","FOX","FUN","FUR",
            "GAP","GAS","GEM","GET","GIG","GIN","GOD","GOT","GUM","GUN",
            "GUY","GYM","HAD","HAM","HAT","HAY","HEM","HEN","HER","HID",
            "HIM","HIP","HIT","HOG","HOP","HOT","HUB","HUG","HUT","ICE",
            "INK","JAM","JAR","JET","JOB","JOG","JOY","JUG","KEY","KID",
            "KIT","LAB","LAD","LAG","LAP","LAW","LEG","LET","LID","LIE",
            "LIP","LOG","LOT","MAD","MAN","MAP","MAT","MAY","MET","MIX",
            "MOB","MOM","MOP","MUD","MUG","NAP","NET","NEW","NOD","NOR",
            "NOT","NOW","NUT","OAK","ODD","OFF","OIL","OLD","ONE","ORB",
            "OUT","OWL","OWN","PAD","PAN","PAT","PAY","PEN","PET","PIG",
            "PIN","PIT","POT","PRO","PUB","PUP","PUT","RAG","RAM","RAN",
            "RAP","RAT","RAW","RED","RIB","RID","RIM","RIP","ROD","ROT",
            "ROW","RUB","RUG","RUN","SAD","SAT","SAW","SEA","SET","SEW",
            "SHE","SHY","SIP","SIR","SIT","SIX","SKY","SLY","SON","SUN",
            "TAB","TAG","TAN","TAP","TAR","TEA","TEN","THE","TIP","TOE",
            "TON","TOP","TOY","TRY","TUB","TUG","TWO","USE","VAN","WAR",
            "WAS","WAX","WAY","WEB","WET","WHO","WHY","WIN","WON","WOW",
            "YAK","YAM","YAP","YEA","YES","YOU","ZIP","ZOO",

            # 4 LETTER WORDS
            "ABLE","ACID","AGED","ALSO","AREA","ARMY","AWAY","BABY","BACK",
            "BALL","BAND","BANK","BASE","BATH","BEAR","BEAT","BEEF","BEEN",
            "BELL","BELT","BEST","BILL","BIRD","BLOW","BLUE","BOAT","BODY",
            "BOMB","BOND","BONE","BOOK","BOOM","BOOT","BORN","BOSS","BOTH",
            "BOWL","BULK","BURN","BUSH","BUSY","CALL","CALM","CAME","CAMP",
            "CARD","CARE","CASE","CASH","CAST","CELL","CHAT","CHIP","CITY",
            "CLUB","COAL","COAT","CODE","COLD","COME","COOK","COOL","COPE",
            "COPY","CORE","COST","CREW","CROP","DARK","DATA","DATE","DAWN",
            "DEAD","DEAL","DEAN","DEAR","DEBT","DEEP","DENY","DESK","DIAL",
            "DICE","DIET","DISC","DISH","DISK","DONE","DOOR","DOWN","DRAW",
            "DREW","DROP","DRUG","DUAL","DUCK","DUST","DUTY","EACH","EARN",
            "EASE","EAST","EASY","EDGE","ELSE","EVEN","EVER","EVIL","EXIT",
            "FACE","FACT","FAIL","FAIR","FALL","FARM","FAST","FATE","FEAR",
            "FEED","FEEL","FELL","FELT","FILE","FILL","FILM","FIND","FINE",
            "FIRE","FIRM","FISH","FIVE","FLAT","FLOW","FOOD","FOOT","FORD",
            "FORM","FORT","FOUR","FREE","FROM","FUEL","FULL","FUND","GAIN",
            "GAME","GATE","GAVE","GEAR","GENE","GIFT","GIRL","GIVE","GLAD",
            "GOAL","GOLD","GOLF","GONE","GOOD","GRAY","GREY","GRID","GROW",
            "HAIR","HALF","HALL","HAND","HANG","HARD","HARM","HATE","HAVE",
            "HEAD","HEAR","HEAT","HELD","HELL","HELP","HERE","HERO","HIGH",
            "HILL","HOLD","HOLE","HOLY","HOME","HOPE","HOST","HOUR","HUGE",
            "HUNG","HUNT","HURT","IDEA","INCH","INTO","IRON","ITEM","JOIN",
            "JUMP","JURY","JUST","KEEP","KEPT","KICK","KILL","KIND","KING",
            "KNEW","KNOW","LACK","LADY","LAID","LAKE","LAND","LANE","LAST",
            "LATE","LEAD","LEFT","LESS","LIFE","LIFT","LIKE","LINE","LINK",
            "LIST","LIVE","LOAD","LOAN","LOCK","LOGO","LONG","LOOK","LORD",
            "LOSE","LOSS","LOST","LOVE","LUCK","MADE","MAIL","MAIN","MAKE",
            "MALE","MANY","MARK","MASS","MATT","MEAL","MEAN","MEAT","MEET",
            "MENU","MERE","MILE","MILK","MIND","MINE","MISS","MODE","MOOD",
            "MOON","MORE","MOST","MOVE","MUCH","MUST","NAME","NAVY","NEAR",
            "NECK","NEED","NEWS","NEXT","NICE","NINE","NONE","NOSE","NOTE",
            "NOTES","OKAY","ONCE","ONLY","ONTO","OPEN","ORAL","OVER","PACE",
            "PACK","PAGE","PAID","PAIN","PAIR","PALM","PARK","PART","PASS",
            "PAST","PATH","PEAK","PICK","PINK","PIPE","PLAN","PLAY","PLOT",
            "PLUG","PLUS","POLL","POOL","POOR","PORT","POST","PULL","PURE",
            "PUSH","RACE","RAID","RAIL","RAIN","RANK","RATE","READ","REAL",
            "REAR","RELY","RENT","REST","RICE","RICH","RIDE","RING","RISE",
            "RISK","ROAD","ROCK","ROLE","ROLL","ROOF","ROOM","ROOT","ROSE",
            "RULE","RUSH","SAFE","SAID","SAKE","SALE","SALT","SAME","SAND",
            "SAVE","SEAT","SEED","SEEK","SEEM","SEEN","SELF","SELL","SEND",
            "SENT","SHIP","SHOP","SHOT","SHOW","SHUT","SICK","SIDE","SIGN",
            "SITE","SIZE","SKIN","SLIP","SLOW","SNOW","SOFT","SOIL","SOLD",
            "SOLE","SOME","SONG","SOON","SORT","SOUL","SPOT","STAR","STAY",
            "STEP","STOP","SUCH","SUIT","SURE","TAKE","TALE","TALK","TALL",
            "TANK","TAPE","TASK","TEAM","TECH","TELL","TEND","TERM","TEST",
            "TEXT","THAN","THAT","THEM","THEN","THEY","THIN","THIS","TIME",
            "TINY","TOLD","TOLL","TONE","TOOK","TOOL","TOUR","TOWN","TREE",
            "TRIP","TRUE","TUNE","TURN","TYPE","UNIT","UPON","USED","USER",
            "VARY","VAST","VERY","VICE","VIEW","VOTE","WAGE","WAIT","WAKE",
            "WALK","WALL","WANT","WARD","WARM","WASH","WAVE","WEAK","WEAR",
            "WEEK","WELL","WENT","WERE","WEST","WHAT","WHEN","WHOM","WIDE",
            "WIFE","WILD","WILL","WIND","WINE","WING","WIRE","WISE","WISH",
            "WITH","WOOD","WORD","WORE","WORK","YARD","YEAH","YEAR","YOUR",
            "ZERO","ZONE",

            # 5 LETTER WORDS
            "ABOUT","ABOVE","ABUSE","ACTOR","ACUTE","ADMIT","ADOPT","ADULT",
            "AFTER","AGAIN","AGENT","AGREE","AHEAD","ALARM","ALBUM","ALERT",
            "ALIEN","ALIGN","ALIKE","ALIVE","ALLOW","ALONE","ALONG","ALTER",
            "AMONG","ANGER","ANGLE","ANGRY","APART","APPLE","APPLY","ARENA",
            "ARGUE","ARISE","ARRAY","ASIDE","ASSET","AUDIO","AVOID","AWARD",
            "AWARE","BADLY","BAKER","BASIC","BASIS","BEACH","BEGAN","BEGIN",
            "BEGUN","BEING","BELOW","BENCH","BIRTH","BLACK","BLAME","BLIND",
            "BLOCK","BLOOD","BOARD","BOOST","BOOTH","BOUND","BRAIN","BRAND",
            "BREAD","BREAK","BREED","BRIEF","BRING","BROAD","BROKE","BROWN",
            "BUILD","BUILT","BUYER","CABLE","CARRY","CATCH","CAUSE","CHAIN",
            "CHAIR","CHART","CHASE","CHEAP","CHECK","CHEST","CHIEF","CHILD",
            "CHINA","CHOSE","CIVIL","CLAIM","CLASS","CLEAN","CLEAR","CLICK",
            "CLOCK","CLOSE","COACH","COAST","COULD","COUNT","COURT","COVER",
            "CRAFT","CRASH","CRIME","CROSS","CROWD","CROWN","CURVE","CYCLE",
            "DAILY","DANCE","DATED","DEALT","DEATH","DEBUT","DELAY","DEPTH",
            "DOING","DOUBT","DOZEN","DRAFT","DRAMA","DRAWN","DREAM","DRESS",
            "DRILL","DRINK","DRIVE","DROVE","DYING","EARLY","EARTH","EIGHT",
            "ELITE","EMPTY","ENEMY","ENJOY","ENTER","ENTRY","EQUAL","ERROR",
            "EVENT","EVERY","EXACT","EXIST","EXTRA","FAITH","FALSE","FAULT",
            "FIBER","FIELD","FIFTH","FIFTY","FIGHT","FINAL","FIRST","FIXED",
            "FLASH","FLEET","FLOOR","FLUID","FOCUS","FORCE","FORTH","FORTY",
            "FORUM","FOUND","FRAME","FRANK","FRAUD","FRESH","FRONT","FRUIT","FULLY",
            "FUNNY","GIANT","GIVEN","GLASS","GLOBE","GOING","GRACE","GRADE",
            "GRAND","GRANT","GRASS","GREEN","GROSS","GROUP","GROWN","GUARD",
            "GUESS","GUEST","GUIDE","HAPPY","HEART","HEAVY","HENCE","HORSE",
            "HOTEL","HOUSE","HUMAN","IDEAL","IMAGE","INDEX","INNER","INPUT",
            "ISSUE","JOINT","JUDGE","KNOWN","LABEL","LARGE","LASER","LATER",
            "LAUGH","LAYER","LEARN","LEASE","LEAST","LEAVE","LEGAL","LEVEL",
            "LIGHT","LIMIT","LOCAL","LOGIC","LOOSE","LOWER","LUCKY","LUNCH",
            "LYING","MAGIC","MAJOR","MAKER","MARCH","MATCH","MAYBE","MAYOR",
            "MEANT","MEDIA","METAL","MIGHT","MINOR","MINUS","MIXED","MODEL",
            "MONEY","MONTH","MORAL","MOTOR","MOUNT","MOUSE","MOUTH","MOVIE",
            "MUSIC","NEVER","NEWLY","NIGHT","NOISE","NORTH","NOTES","NOVEL",
            "NURSE","OCCUR","OCEAN","OFFER","OFTEN","ORDER","OTHER","OUGHT",
            "PAINT","PANEL","PAPER","PARTY","PEACE","PHASE","PHONE","PHOTO",
            "PIECE","PILOT","PITCH","PLACE","PLAIN","PLANE","PLANT","PLATE",
            "POINT","POUND","POWER","PRESS","PRICE","PRIDE","PRIME","PRINT",
            "PRIOR","PRIZE","PROOF","PROUD","PROVE","QUEEN","QUICK","QUIET",
            "QUITE","RADIO","RAISE","RANGE","RAPID","RATIO","REACH","READY",
            "REFER","RIGHT","RIVAL","RIVER","ROMAN","ROUGH","ROUND","ROUTE",
            "ROYAL","RURAL","SCALE","SCENE","SCOPE","SCORE","SENSE","SERVE",
            "SEVEN","SHALL","SHAPE","SHARE","SHARP","SHEET","SHELF","SHELL",
            "SHIFT","SHINE","SHIRT","SHOCK","SHOOT","SHORT","SHOWN","SIGHT",
            "SINCE","SIXTH","SIXTY","SKILL","SLEEP","SLIDE","SMALL","SMART",
            "SMILE","SMOKE","SOLID","SOLVE","SORRY","SOUND","SOUTH","SPACE",
            "SPARE","SPEAK","SPEED","SPEND","SPENT","SPLIT","SPORT","STAFF",
            "STAGE","STAKE","STAND","START","STATE","STEAM","STEEL","STICK",
            "STILL","STOCK","STONE","STOOD","STORE","STORM","STORY","STRIP",
            "STUCK","STUDY","STUFF","STYLE","SUGAR","SUITE","SUPER","SWEET",
            "TABLE","TAKEN","TASTE","TEACH","THANK","THEFT","THEIR","THEME",
            "THERE","THESE","THICK","THING","THINK","THIRD","THREE","THREW","THROW",
            "TIGHT","TITLE","TODAY","TOPIC","TOTAL","TOUCH","TOUGH","TOWER",
            "TRACK","TRADE","TRAIN","TREAT","TREND","TRIAL","TRIED","TRUCK",
            "TRULY","TRUST","TRUTH","TWICE","UNDER","UNDUE","UNION","UNITY",
            "UNTIL","UPPER","UPSET","URBAN","USAGE","USUAL","VALID","VALUE",
            "VIDEO","VIRUS","VISIT","VITAL","VOICE","WASTE","WATCH","WATER",
            "WHEEL","WHERE","WHICH","WHILE","WHITE","WHOLE","WHOSE","WOMAN",
            "WORLD","WORRY","WORSE","WORST","WORTH","WOULD","WRITE","WRONG",
            "WROTE","YOUNG","YOUTH"
        ]

        found = []

        for row in board:
            line = "".join([c if c else " " for c in row])
            found += self.find_words(line, dictionary, used)

        for col in range(5):
            line = "".join([
                board[r][col] if board[r][col] else " "
                for r in range(5)
            ])
            found += self.find_words(line, dictionary, used)

        return found

    def find_words(self, line, dictionary, used):

        found = []

        for i in range(len(line)):
            for j in range(i+2, len(line)+1):
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