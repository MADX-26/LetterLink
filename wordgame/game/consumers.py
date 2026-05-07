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
                        "AN","AM","AS","AT","BE","BY","DO","GO","HE","HI",
            "IF","IN","IS","IT","ME","MY","NO","OF","ON","OR",
            "OX","SO","TO","UP","US","WE",

            "ACE","ACT","ADD","AGE","AIR","ALL","AND","ANT","ANY","APE",
            "APP","ARC","ARM","ART","ASH","ASK","AWE","AXE","BAD","BAG",
            "BAR","BAT","BAY","BED","BEE","BET","BID","BIG","BIN","BIT",
            "BOB","BOG","BON","BOX","BOY","BUN","BUS","BUT","CAB","CAN",
            "CAP","CAR","CAT","CUP","CUT","DAD","DAM","DAY","DEN","DID",
            "DIG","DIM","DIN","DIP","DOG","DOT","DRY","DUE","EAR","EAT",
            "EGG","END","ERA","EYE","FAN","FAR","FAT","FAX","FED","FEW",
            "FIG","FIN","FIT","FIX","FLY","FOG","FOX","FUN","FUR","GAP",
            "GAS","GEM","GET","GIG","GIN","GOD","GOT","GUM","GUN","GUY",
            "GYM","HAD","HAM","HAT","HAY","HEM","HEN","HER","HID","HIM",
            "HIP","HIT","HOG","HOP","HOT","HUB","HUG","HUT","ICE","INK",
            "JAM","JAR","JET","JOB","JOG","JOY","JUG","KEY","KID","KIT",
            "LAB","LAD","LAG","LAP","LAW","LEG","LET","LID","LIE","LIP",
            "LOG","LOT","MAD","MAN","MAP","MAT","MAY","MEN","MET","MIX",
            "MOB","MOP","MUD","MUG","NAP","NET","NEW","NOD","NON","NOR",
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

            "ABLE","ACID","AGED","ALSO","AREA","ARMY","AWAY","BABY","BACK","BALL",
            "BAND","BANK","BASE","BATH","BEAR","BEAT","BEEF","BEEN","BELL","BELT",
            "BEST","BILL","BIRD","BLOW","BLUE","BOAT","BODY","BOMB","BOND","BONE",
            "BOOK","BOOM","BOOT","BORN","BOSS","BOTH","BOWL","BULK","BURN","BUSH",
            "BUSY","CALL","CALM","CAME","CAMP","CARD","CARE","CASE","CASH","CAST",
            "CELL","CHAT","CHIP","CITY","CLUB","COAL","COAT","CODE","COLD","COME",
            "COOK","COOL","COPE","COPY","CORE","COST","CREW","CROP","DARK","DATA",
            "DATE","DAWN","DEAD","DEAL","DEAN","DEAR","DEBT","DEEP","DENY","DESK",
            "DIAL","DICE","DIET","DISC","DISH","DISK","DOES","DONE","DOOR","DOWN",
            "DRAW","DREW","DROP","DRUG","DUAL","DUCK","DUST","DUTY","EACH","EARN",
            "EASE","EAST","EASY","EDGE","ELSE","EVEN","EVER","EVIL","EXIT","FACE",
            "FACT","FAIL","FAIR","FALL","FARM","FAST","FATE","FEAR","FEED","FEEL",
            "FEET","FELL","FELT","FILE","FILL","FILM","FIND","FINE","FIRE","FIRM",
            "FISH","FIVE","FLAT","FLOW","FOOD","FOOT","FORD","FORM","FORT","FOUR",
            "FREE","FROM","FUEL","FULL","FUND","GAIN","GAME","GATE","GAVE","GEAR",
            "GENE","GIFT","GIRL","GIVE","GLAD","GOAL","GOES","GOLD","GOLF","GONE",
            "GOOD","GRAY","GREY","GRID","GROW","HAIR","HALF","HALL","HAND","HANG",
            "HARD","HARM","HATE","HAVE","HEAD","HEAR","HEAT","HELD","HELL","HELP",
            "HERE","HERO","HIGH","HILL","HOLD","HOLE","HOLY","HOME","HOPE","HOST",
            "HOUR","HUGE","HUNG","HUNT","HURT","IDEA","INCH","INTO","IRON","ITEM",
            "JACK","JANE","JEAN","JOIN","JUMP","JURY","JUST","KEEP","KENT","KEPT",
            "KICK","KILL","KIND","KING","KNEW","KNOW","LACK","LADY","LAID","LAKE",
            "LAND","LANE","LAST","LATE","LEAD","LEFT","LESS","LIFE","LIFT","LIKE",
            "LINE","LINK","LIST","LIVE","LOAD","LOAN","LOCK","LOGO","LONG","LOOK",
            "LORD","LOSE","LOSS","LOST","LOVE","LUCK","MADE","MAIL","MAIN","MAKE",
            "MALE","MANY","MARK","MASS","MATT","MEAL","MEAN","MEAT","MEET","MENU",
            "MERE","MIKE","MILE","MILK","MIND","MINE","MISS","MODE","MOOD","MOON",
            "MORE","MOST","MOVE","MUCH","MUST","NAME","NAVY","NEAR","NECK","NEED",
            "NEWS","NEXT","NICE","NICK","NINE","NONE","NOSE","NOTE","OKAY","ONCE",
            "ONLY","ONTO","OPEN","ORAL","OVER","PACE","PACK","PAGE","PAID","PAIN",
            "PAIR","PALM","PARK","PART","PASS","PAST","PATH","PEAK","PICK","PINK",
            "PIPE","PLAN","PLAY","PLOT","PLUG","PLUS","POLL","POOL","POOR","PORT",
            "POST","PULL","PURE","PUSH","RACE","RAIL","RAIN","RANK","RATE","READ",
            "REAL","REAR","RELY","RENT","REST","RICE","RICH","RIDE","RING","RISE",
            "RISK","ROAD","ROCK","ROLE","ROLL","ROOF","ROOM","ROOT","ROSE","RULE",
            "RUSH","RUTH","SAFE","SAID","SAKE","SALE","SALT","SAME","SAND","SAVE",
            "SEAT","SEED","SEEK","SEEM","SEEN","SELF","SELL","SEND","SENT","SHIP",
            "SHOP","SHOT","SHOW","SHUT","SICK","SIDE","SIGN","SITE","SIZE","SKIN",
            "SLIP","SLOW","SNOW","SOFT","SOIL","SOLD","SOLE","SOME","SONG","SOON",
            "SORT","SOUL","SPOT","STAR","STAY","STEP","STOP","SUCH","SUIT","SURE",
            "TAKE","TALE","TALK","TALL","TANK","TAPE","TASK","TEAM","TECH","TELL",
            "TEND","TERM","TEST","TEXT","THAN","THAT","THEM","THEN","THEY","THIN",
            "THIS","TIME","TINY","TOLD","TOLL","TONE","TONY","TOOK","TOOL","TOUR",
            "TOWN","TREE","TRIP","TRUE","TUNE","TURN","TYPE","UNIT","UPON","USED",
            "USER","VARY","VAST","VERY","VICE","VIEW","VOTE","WAGE","WAIT","WAKE",
            "WALK","WALL","WANT","WARD","WARM","WASH","WAVE","WAYS","WEAK","WEAR",
            "WEEK","WELL","WENT","WERE","WEST","WHAT","WHEN","WHOM","WIDE","WIFE",
            "WILD","WILL","WIND","WINE","WING","WIRE","WISE","WISH","WITH","WOOD",
            "WORD","WORE","WORK","YARD","YEAH","YEAR","YOUR","ZERO","ZONE",

            "ABOUT","ABOVE","ABUSE","ACTOR","ACUTE","ADMIT","ADOPT","ADULT","AFTER","AGAIN",
            "AGENT","AGREE","AHEAD","ALARM","ALBUM","ALERT","ALIEN","ALIGN","ALIKE","ALIVE",
            "ALLOW","ALONE","ALONG","ALTER","AMONG","ANGER","ANGLE","ANGRY","APART","APPLE",
            "APPLY","ARENA","ARGUE","ARISE","ARRAY","ASIDE","ASSET","AUDIO","AVOID","AWARD",
            "AWARE","BADLY","BAKER","BASES","BASIC","BASIS","BEACH","BEGAN","BEGIN","BEGUN",
            "BEING","BELOW","BENCH","BILLY","BIRTH","BLACK","BLAME","BLIND","BLOCK","BLOOD",
            "BOARD","BOOST","BOOTH","BOUND","BRAIN","BRAND","BREAD","BREAK","BREED","BRIEF",
            "BRING","BROAD","BROKE","BROWN","BUILD","BUILT","BUYER","CABLE","CARRY","CATCH",
            "CAUSE","CHAIN","CHAIR","CHART","CHASE","CHEAP","CHECK","CHEST","CHIEF","CHILD",
            "CHINA","CHOSE","CIVIL","CLAIM","CLASS","CLEAN","CLEAR","CLICK","CLOCK","CLOSE",
            "COACH","COAST","COULD","COUNT","COURT","COVER","CRAFT","CRASH","CRIME","CROSS",
            "CROWD","CROWN","CURVE","CYCLE","DAILY","DANCE","DATED","DEALT","DEATH","DEBUT",
            "DELAY","DEPTH","DOING","DOUBT","DOZEN","DRAFT","DRAMA","DRAWN","DREAM","DRESS",
            "DRILL","DRINK","DRIVE","DROVE","DYING","EARLY","EARTH","EIGHT","ELITE","EMPTY",
            "ENEMY","ENJOY","ENTER","ENTRY","EQUAL","ERROR","EVENT","EVERY","EXACT","EXIST",
            "EXTRA","FAITH","FALSE","FAULT","FIBER","FIELD","FIFTH","FIFTY","FIGHT","FINAL",
            "FIRST","FIXED","FLASH","FLEET","FLOOR","FLUID","FOCUS","FORCE","FORTH","FORTY",
            "FORUM","FOUND","FRAME","FRANK","FRAUD","FRESH","FRONT","FRUIT","FULLY","FUNNY",
            "GIANT","GIVEN","GLASS","GLOBE","GOING","GRACE","GRADE","GRAND","GRANT","GRASS",
            "GREEN","GROSS","GROUP","GROWN","GUARD","GUESS","GUEST","GUIDE","HAPPY","HARRY",
            "HEART","HEAVY","HENCE","HENRY","HORSE","HOTEL","HOUSE","HUMAN","IDEAL","IMAGE",
            "INDEX","INNER","INPUT","ISSUE","JAPAN","JIMMY","JOINT","JONES","JUDGE","KNOWN",
            "LABEL","LARGE","LASER","LATER","LAUGH","LAYER","LEARN","LEASE","LEAST","LEAVE",
            "LEGAL","LEVEL","LEWIS","LIGHT","LIMIT","LOCAL","LOGIC","LOOSE","LOWER","LUCKY",
            "LUNCH","LYING","MAGIC","MAJOR","MAKER","MARCH","MARIA","MATCH","MAYBE","MAYOR",
            "MEANT","MEDIA","METAL","MIGHT","MINOR","MINUS","MIXED","MODEL","MONEY","MONTH",
            "MORAL","MOTOR","MOUNT","MOUSE","MOUTH","MOVIE","MUSIC","NEEDS","NEVER","NEWLY",
            "NIGHT","NOISE","NORTH","NOTED","NOTES","NOVEL","NURSE","OCCUR","OCEAN","OFFER",
            "OFTEN","ORDER","OTHER","OUGHT","PAINT","PANEL","PAPER","PARTY","PEACE","PETER",
            "PHASE","PHONE","PHOTO","PIECE","PILOT","PITCH","PLACE","PLAIN","PLANE","PLANT",
            "PLATE","POINT","POUND","POWER","PRESS","PRICE","PRIDE","PRIME","PRINT","PRIOR",
            "PRIZE","PROOF","PROUD","PROVE","QUEEN","QUICK","QUIET","QUITE","RADIO","RAISE",
            "RANGE","RAPID","RATIO","REACH","READY","REFER","RIGHT","RIVAL","RIVER","ROBIN",
            "ROGER","ROMAN","ROUGH","ROUND","ROUTE","ROYAL","RURAL","SCALE","SCENE","SCOPE",
            "SCORE","SENSE","SERVE","SEVEN","SHALL","SHAPE","SHARE","SHARP","SHEET","SHELF",
            "SHELL","SHIFT","SHINE","SHIRT","SHOCK","SHOOT","SHORT","SHOWN","SIGHT","SINCE",
            "SIXTH","SIXTY","SIZED","SKILL","SLEEP","SLIDE","SMALL","SMART","SMILE","SMITH",
            "SMOKE","SOLID","SOLVE","SORRY","SOUND","SOUTH","SPACE","SPARE","SPEAK","SPEED",
            "SPEND","SPENT","SPLIT","SPORT","STAFF","STAGE","STAKE","STAND","START","STATE",
            "STEAM","STEEL","STICK","STILL","STOCK","STONE","STOOD","STORE","STORM","STORY",
            "STRIP","STUCK","STUDY","STUFF","STYLE","SUGAR","SUITE","SUPER","SWEET","TABLE",
            "TAKEN","TASTE","TAXES","TEACH","TEETH","TERRY","TEXAS","THANK","THEFT","THEIR",
            "THEME","THERE","THESE","THICK","THING","THINK","THIRD","THOSE","THREE","THREW",
            "THROW","TIGHT","TIMES","TIRED","TITLE","TODAY","TOPIC","TOTAL","TOUCH","TOUGH",
            "TOWER","TRACK","TRADE","TRAIN","TREAT","TREND","TRIAL","TRIED","TRIES","TRUCK",
            "TRULY","TRUST","TRUTH","TWICE","UNDER","UNDUE","UNION","UNITY","UNTIL","UPPER",
            "UPSET","URBAN","USAGE","USUAL","VALID","VALUE","VIDEO","VIRUS","VISIT","VITAL",
            "VOICE","WASTE","WATCH","WATER","WHEEL","WHERE","WHICH","WHILE","WHITE","WHOLE",
            "WHOSE","WOMAN","WOMEN","WORLD","WORRY","WORSE","WORST","WORTH","WOULD","WRITE",
            "WRONG","WROTE","YOUNG","YOUTH"
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