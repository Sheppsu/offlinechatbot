# coding=utf-8

# TODO: clean up code in general
#       utilize DMs (maybe)
#       make decorators for osu arguments
#       implement rate limit for unverified bot
#       save bans to database so they can be made with a command and also check via user id
#       try communicating with the mysql server more instead of saving data locally
from dotenv import load_dotenv
load_dotenv()

from get_top_players import Client
from get_popular_anime import create_list as create_anime_list
from sql import Database, USER_SETTINGS
from emotes import EmoteRequester
from helper_objects import *
from context import *
from util import *
from constants import *

import websockets
import os
import sys
from client import Bot as CommunicationClient
from osu import AsynchronousClient, GameModeStr, Mods, Mod, GameModeInt, SoloScore, ScoreDataStatistics
from osu_diff_calc import OsuPerformanceCalculator, OsuDifficultyAttributes, OsuScoreAttributes
from pytz import timezone, all_timezones
from copy import deepcopy
from aiohttp import client_exceptions
from datetime import datetime, timezone as tz


TESTING = "--test" in sys.argv
LOCAL = "-local" in sys.argv

if not TESTING or not os.path.exists("data/top players (200).json"):
    Client().run()  # Update top player json file
if not TESTING or not os.path.exists("data/anime.json"):
    create_anime_list()
if not TESTING or not os.path.exists("data/azur_lane.json"):
    from azur_lane import download_azur_lane_ship_names
    download_azur_lane_ship_names()

command_manager = CommandManager()


class Bot:
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    username = "sheppsubot"
    oauth = os.getenv("OAUTH")
    uri = "ws://irc-ws.chat.twitch.tv:80"

    restarts = 0

    def __init__(self, cm):
        self.database = Database()
        channels_to_run_in = [ChannelConfig("sheppsu", 156710598)] if TESTING else self.database.get_channels()

        self.cm = cm
        self.cm.init(self, channels_to_run_in)

        self.ws = None
        # self.comm_client = CommunicationClient(self)
        self.running = False
        self.loop = asyncio.get_event_loop()
        self.last_message = {}
        self.own_state = None
        self.irc_command_handlers = {
            ContextType.CONNECTED: self.on_running,
            ContextType.PRIVMSG: self.on_message,
            ContextType.USERSTATE: self.on_user_state,
            ContextType.JOIN: self.on_join,
        }

        # Is ed offline or not
        self.offlines = {channel: True for channel in self.cm.channels}

        # Twitch api stuff
        self.access_token, self.expire_time = self.get_access_token()
        self.expire_time += perf_counter()

        # Message related variables
        self.message_send_cd = 1.5
        self.message_locks = {}

        # Data from files
        self.top_players = []
        self.top_maps = []
        self.word_list = []
        self.pull_options = {}
        self.all_words = []
        self.anime = []
        self.azur_lane = []

        # cache data
        self.afks = []
        self.osu_user_id_cache = {}

        # Load save data
        self.load_data()
        self.genshin = self.pull_options["3"] + self.pull_options["4"] + self.pull_options["5"]

        # Guess the number
        self.number = random.randint(1, 1000)

        # Trivia
        self.trivia_helpers = {}

        self.scrambles = {
            "word": Scramble("word", lambda: random.choice(self.word_list), 1),
            "osu": Scramble("player name", lambda: random.choice(self.top_players), 0.8),
            "map": Scramble("map name", lambda: random.choice(self.top_maps), 1.3),
            "genshin": Scramble("genshin weap/char", lambda: random.choice(self.genshin), 0.7),
            # "emote": Scramble("emote", lambda channel: random.choice(self.emotes[channel]).name, 0.7,
            #                   ScrambleHintType.EVERY_OTHER, True, ScrambleRewardType.LOGARITHM),
            "anime": Scramble("anime", lambda: random.choice(self.anime[:250]), 1.1),
            "al": Scramble("azurlane ship", lambda: random.choice(self.azur_lane), 0.9),
        }
        self.scramble_manager = ScrambleManager(self.scrambles)

        # emote stuff
        # self.emote_requester = EmoteRequester(self.client_id, self.client_secret)
        # self.emote_requester.http.set_access_token(self.access_token)
        self.emotes = {channel: [] for channel in self.cm.channels}  # {channel: sum(self.emote_requester.get_channel_emotes(channel), []) for channel in self.cm.channels}

        # Bomb party
        self.bomb_party_helper = BombParty()
        self.bomb_party_future = None
        self.exploding = False

        # Anime compare
        self.compare_helper = AnimeCompare(self.anime)
        self.anime_compare_future = {}

        # osu! stuff
        self.recent_score_cache = {}

        # timezone stuff
        self.tz_abbreviations = {}
        for name in all_timezones:
            tzone = timezone(name)
            for _, _, abbr in getattr(tzone, "_transition_info", [[None, None, datetime.now(tzone).tzname()]]):
                if abbr not in self.tz_abbreviations:
                    self.tz_abbreviations[abbr] = []
                if name in self.tz_abbreviations[abbr]:
                    continue
                self.tz_abbreviations[abbr].append(name)

        self.osu_client = AsynchronousClient.from_osu_credentials(
            os.getenv("OSU_USERNAME"), os.getenv("OSU_PASSWORD"),
            request_wait_time=0, limit_per_minute=1200
        )
        self.osu_client.http.use_lazer = False
        self.osu_lock = asyncio.Lock()

        self.message_buffer = []

    # Util

    def set_timed_event(self, wait, callback, *args, **kwargs):
        future = asyncio.run_coroutine_threadsafe(do_timed_event(wait, callback, *args, **kwargs), self.loop)
        future.add_done_callback(future_callback)
        return future

    async def create_periodic_message(self, channel, message, wait_time, offset):
        async def send_message():
            await self.send_message(channel, message)
            self.set_timed_event(wait_time, send_message)

        if offset == 0:
            await send_message()
        else:
            self.set_timed_event(offset, send_message)

    def get_wait_for_channel(self, channel):
        # TODO: make a check for if the bot is a moderator in the channel
        if channel == self.username or (self.own_state is not None and self.own_state.mod):
            return 0.3
        return 1.5

    @staticmethod
    def get_partial_ctx(username, user_id):
        return namedtuple("PartialMessageContext", ("sending_user", "user_id"))(username, user_id)

    # File save/load

    def load_top_players(self):
        with open("data/top players (200).json", "r") as f:
            self.top_players = json.load(f)

    def load_top_maps(self):
        with open("data/top_maps.json", "r") as f:
            self.top_maps = json.load(f)

    def load_words(self):
        with open("data/words.json", "r") as f:
            self.word_list = json.load(f)

    def load_all_words(self):
        with open("data/all_words.json", "r") as f:
            self.all_words = [word.lower() for word in json.load(f)]

    def load_anime(self):
        with open("data/anime.json", "r") as f:
            self.anime = json.load(f)

    def load_azur_lane(self):
        with open("data/azur_lane.json", "r") as f:
            self.azur_lane = json.load(f)

    async def reload_channels(self):
        if TESTING:
            return print("Cannot reload channels in testing mode")
        current_channels = set([channel.id for channel in self.cm.channels.values()])
        channels = self.database.get_channels()
        channel_ids = set([channel.id for channel in channels])
        leave_channels = current_channels - channel_ids
        join_channels = channel_ids - current_channels
        for channel in channels:
            if channel.id in leave_channels:
                await self.part(channel.name)
            elif channel.id in join_channels:
                await self.join(channel.name)
        self.cm.load_channels(channels)

    def load_genshin(self):
        with open("data/genshin.json", "r") as f:
            self.pull_options = json.load(f)

    def load_data(self):
        self.load_top_players()
        self.load_top_maps()
        self.load_words()
        self.load_all_words()
        self.load_genshin()
        self.load_anime()
        self.load_azur_lane()
        self.afks = list(self.database.get_afks())

    # Api request stuff
    # TODO: consider moving api stuff to its own class

    def load_top_plays(self):  # To be used in the future maybe
        resp = requests.get('https://osutrack-api.ameo.dev/bestplay?mode=0')
        resp.raise_for_status()
        top_plays = resp.json()

    def get_access_token(self):
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        resp = requests.post("https://id.twitch.tv/oauth2/token", params=params)
        resp.raise_for_status()
        resp = resp.json()
        return resp['access_token'], resp['expires_in']

    def get_stream_status(self, channel):
        try:
            params = {"query": channel, "first": 1}
            headers = {"Authorization": f"Bearer {self.access_token}", "Client-Id": self.client_id}
            resp = requests.get("https://api.twitch.tv/helix/search/channels", params=params, headers=headers)
            resp.raise_for_status()
            resp = resp.json()
            self.offlines[channel] = not resp['data'][0]['is_live']
        except:
            print(traceback.format_exc())
            self.offlines[channel] = False

    def get_streams_test(self):
        # TODO: finishing later I gtg now...
        # TODO: account for limit of 100
        channels = list(map(lambda c: c.id, filter(lambda c: c.offlineonly, self.cm.channels.values())))
        params = {"user_id": channels}
        headers = {"Authorization": f"Bearer {self.access_token}", "Client-Id": self.client_id}
        print(params)
        resp = requests.get("https://api.twitch.tv/helix/streams", params=params, headers=headers)
        data = resp.json()
        print(data["data"])

    # Fundamental

    async def start(self):
        async with websockets.connect(self.uri) as ws:
            self.ws = ws
            self.running = True

            try:
                # Start up
                await self.connect()  # Connect to the irc server
                poll = asyncio.run_coroutine_threadsafe(self.poll(), self.loop)  # Begin polling for events sent by the server
                # if not TESTING:
                #     comm = asyncio.run_coroutine_threadsafe(self.comm_client.run(), self.loop)  # Start the client that communicates with remote clients

                # Running loop
                last_check = perf_counter() - 20
                last_ping = perf_counter() - 60*60  # 1 hour
                last_update = perf_counter() - 60
                # comm_done = False
                while self.running:
                    await asyncio.sleep(1)  # Leave time for other stuff to run

                    # Check if channels are live
                    if perf_counter() - last_check >= 20:
                        for channel in self.cm.channels.values():
                            if not channel.offlineonly:
                                continue
                            self.get_stream_status(channel.name)
                        last_check = perf_counter()

                    # Check if access token needs to be renewed
                    if perf_counter() >= self.expire_time:
                        self.access_token, self.expire_time = self.get_access_token()
                        self.expire_time += perf_counter()

                    # Ping database once an hour for keepalive
                    if perf_counter() - last_ping >= 60*60:
                        last_ping = perf_counter()
                        self.database.ping()

                    if perf_counter() - last_update >= 60*60:
                        last_update = perf_counter()
                        create_anime_list()
                        self.load_anime()

                    # Check if poll is no longer running, in which case, the bot is no longer running.
                    if poll.done():
                        print(poll.result())
                        self.running = False

                    # if not TESTING and comm.done() and not comm_done:
                    #     comm_done = True
                    #     try:
                    #         print("Communication client finished")
                    #         print(comm.result())
                    #     except:
                    #         traceback.print_exc()

            except KeyboardInterrupt:
                pass
            except websockets.ConnectionClosedError as e:
                # Restart the bot
                print(e)
                if self.restarts < 5:
                    self.restarts += 1
                    print("Restarting bot...")
                    await self.start()
            except:
                print(traceback.format_exc())
        self.running = False

    async def connect(self):
        await self.ws.send(f"PASS {self.oauth}")
        print(f"> PASS {self.oauth}")
        await self.ws.send(f"NICK {self.username}")
        print(f"> NICK {self.username}")

    async def poll(self):
        while self.running:
            data = await self.ws.recv()
            print(f"< {data}")

            if data.startswith("PING"):
                await self.ws.send("PONG :tmi.twitch.tv")
                continue

            # Account for tags
            ctxs = Context(data)

            for ctx in ctxs:
                for cmd, handler in self.irc_command_handlers.items():
                    if ctx.type == cmd:
                        future = asyncio.run_coroutine_threadsafe(handler(ctx), self.loop)
                        future.add_done_callback(future_callback)

    async def join(self, channel):
        channel = channel.lower()
        await self.ws.send(f"JOIN #{channel}")
        print(f"> JOIN #{channel}")

    async def part(self, channel):
        await self.ws.send(f"PART #{channel}\r\n")
        print(f"< PART #{channel}\r\n")

    async def register_cap(self, *caps):
        caps = ' '.join([f'twitch.tv/{cap}' for cap in caps])
        await self.ws.send(f"CAP REQ :{caps}\r\n")
        print(f"< CAP REQ :{caps}\r\n")

    async def send_message(self, channel, message):
        message = message.strip()
        while (i := message.find("  ")) != -1:
            message = message[:i] + message[i+1:]

        # TODO: fix rate limit handling shit
        if channel in self.offlines and not self.offlines[channel]:
            return
        await self.message_locks[channel].acquire()
        messages = split_message(message)
        sent_messages = []
        for msg in messages:
            cmd = f"PRIVMSG #{channel} :/me " + msg + (" \U000e0000" if self.last_message[channel] == msg else "")
            await self.ws.send(cmd)
            self.last_message[channel] = msg
            print(f"> "+cmd)
            sent_messages.append(msg.strip())
            await asyncio.sleep(self.get_wait_for_channel(channel))  # Avoid going over ratelimits
        self.message_locks[channel].release()
        return sent_messages

    # IRC command handlers

    async def on_running(self, ctx):
        await self.register_cap("tags")
        await self.register_cap("commands")
        for channel in self.cm.channels:
            await self.join(channel)

    async def on_user_state(self, ctx: UserStateContext):
        if ctx.username == self.username:
            self.own_state = ctx

    async def on_join(self, ctx: JoinContext):
        self.message_locks[ctx.channel] = asyncio.Lock()
        self.last_message[ctx.channel] = ""
        self.emotes[ctx.channel] = []  # sum(self.emote_requester.get_channel_emotes(ctx.channel), [])
        self.offlines[ctx.channel] = True
        self.recent_score_cache[ctx.channel] = {}
        self.trivia_helpers[ctx.channel] = TriviaHelper()

    async def on_message(self, ctx: MessageContext):
        if (ctx.channel in self.offlines and not self.offlines[ctx.channel]) or \
                ctx.user.username == self.username:
            return

        if ctx.message.lower().startswith("pogpega") and ctx.message.lower() != "pogpega":
            ctx.message = ctx.message[8:]

        ascii_message = "".join([char for char in ctx.message if char.isascii()]).strip()

        for scramble_type, scramble in self.scrambles.items():
            if scramble.in_progress(ctx.channel):
                await self.on_scramble(ctx, scramble_type)

        if ctx.user.username in self.anime_compare_future and self.anime_compare_future[ctx.user.username] is not None and \
                ascii_message.isdigit() and int(ascii_message.strip()) in range(1, 3):
            game = self.compare_helper.get_game(ctx.user.username)
            if game is not None:
                await self.on_anime_compare(ctx, game)

        elif self.trivia_helpers[ctx.channel].is_in_progress and ascii_message.isdigit() and \
                int(ascii_message.strip()) in range(1, 5):
            message = int(ascii_message)
            await self.on_answer(ctx, message)

        if self.bomb_party_helper.started:
            await self.on_bomb_party(ctx)

        await self.on_afk(ctx)

        if ctx.reply:
            ascii_message = " ".join(ascii_message.split()[1:])
            ctx.message = " ".join(ctx.message.split()[1:])

        if ascii_message.startswith("!"):
            command = ascii_message.split()[0].lower().replace("!", "")
            await self.cm(command, ctx)  # Automatically checks that the command exists

    # Commands

    @command_manager.command("pull", Cooldown(1, 2), aliases=["genshinpull"])
    async def pull(self, ctx):
        # TODO: Try and make this look more clean
        user = ctx.user.username
        pity = self.database.get_user_pity(user)
        if pity is None:
            pity = (0, 0)
            self.database.new_pity(user, 0, 0)
        hit_pity = False
        pity = (pity[0]+1, pity[1]+1)
        if pity[0] == 10 and pity[1] != 90:
            pull = 4
            hit_pity = True
        elif pity[1] == 90:
            pull = 5
            hit_pity = True
        else:
            num = random.randint(1, 1000)
            pull = 3
            if num <= (300 - 20 * (pity[1] - 76) if pity[1] >= 76 else 6):
                pull = 5
            elif num <= 57:
                pull = 4
        await self.send_message(ctx.channel,
                                f"@{user} You pulled {random.choice(self.pull_options[str(pull)])} " +
                                ("\u2B50\u2B50\u2B50" if pull == 3 else '🌟' * pull) +
                                {3: ". 😔", 4: "! Pog", 5: "! PogYou"}[pull] +
                                ((" Rolls in: " + str(
                                   pity[pull-4] if hit_pity else {4: 10, 5: 90}[pull])) if pull != 3 else "")
                                )
        if pull == 5:
            pity = (0, 0)
        elif pull == 4:
            pity = (0, pity[1])
        self.database.save_pity(user, pity[0], pity[1])

    @command_manager.command("font")
    async def font(self, ctx):
        args = ctx.get_args()
        if len(args) < 2:
            return await self.send_message(ctx.channel, "Must provide a font name and characters to convert. Do !fonts to see a list of valid fonts.")

        font_name = args[0].lower()
        if font_name not in fonts:
            return await self.send_message(ctx.channel, f"{font_name} is not a valid font name.")

        await self.send_message(ctx.channel, "".join([fonts[font_name][layout.index(char)] if char in layout else char for char in " ".join(args[1:])]))

    @command_manager.command("fonts")
    async def fonts(self, ctx):
        await self.send_message(ctx.channel, f'Valid fonts: {", ".join(list(fonts.keys()))}.')

    @command_manager.command("guess", Cooldown(2, 3))
    async def guess(self, ctx):
        args = ctx.get_args()
        if len(args) < 1:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} You must provide a number 1-1000 to guess with")

        if not args[0].isdigit():
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} That's not a valid number OuttaPocket Tssk")

        guess = int(args[0])

        if self.number == guess:
            await self.send_message(ctx.channel, f"@{ctx.user.display_name} You got it PogYou")
            self.number = random.randint(1, 1000)
        else:
            await self.send_message(ctx.channel, f"@{ctx.user.display_name} It's not {guess}. Try guessing " + (
                "higher" if guess < self.number else "lower") + ". veryPog")

    # TODO: consider putting trivia stuff in its own class
    @command_manager.command("trivia")
    async def trivia(self, ctx):
        if self.trivia_helpers[ctx.channel].is_in_progress:
            return

        args = ctx.get_args("ascii")
        question = self.trivia_helpers[ctx.channel].generate_question(args[0] if len(args) > 0 else None)
        if question is None:
            return await self.send_message(ctx.channel, "An error occurred when attempting to fetch the question...")
        await self.send_message(ctx.channel, question)

        self.trivia_helpers[ctx.channel].future = self.set_timed_event(20, self.on_trivia_finish, ctx.channel)

    async def on_answer(self, ctx, answer):
        result = self.trivia_helpers[ctx.channel].check_guess(ctx, answer)
        if result is None:
            return
        message, amount = result
        await self.send_message(ctx.channel, message)
        self.database.add_money(ctx, amount)

    async def on_trivia_finish(self, channel):
        self.trivia_helpers[channel].reset(cancel=False)
        await self.send_message(channel, "Time has run out for the trivia.")

    @command_manager.command("slap")
    async def slap(self, ctx):
        args = ctx.get_args()
        if not args:
            return

        hit = random.choice((True, False))
        await self.send_message(ctx.channel,
                                f"{ctx.user.username} slapped {args[0]}! D:" if hit else f"{ctx.user.username} tried to slap {args[0]}, but they caught it! pepePoint")

    @command_manager.command("pity")
    async def pity(self, ctx):
        pity = self.database.get_user_pity(ctx.sending_user)
        if pity is None:
            return await self.send_message(ctx.channel, "You haven't rolled yet (from the time the bot started up).")
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} 4* pity in {10 - pity[0]} rolls; "
                                             f"5* pity in {90 - pity[1]} rolls.")

    @command_manager.command("scramble", fargs=["word"])
    @command_manager.command("scramble_osu", fargs=["osu"])
    @command_manager.command("scramble_map", fargs=["map"])
    @command_manager.command("scramble_emote", fargs=["emote"])
    @command_manager.command("scramble_genshin", fargs=["genshin"])
    @command_manager.command("scramble_anime", fargs=["anime"])
    @command_manager.command("scramble_al", fargs=["al"])
    async def scramble(self, ctx, scramble_type):
        if self.scramble_manager.in_progress(scramble_type, ctx.channel):
            return
        if scramble_type == "emote" and len(self.emotes[ctx.channel]) < 20:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Must have at least 20 emotes "
                                                        "in this channel to use the emote scramble.")

        scrambled_word = self.scramble_manager.get_scramble(scramble_type, ctx.channel)
        await self.send_message(ctx.channel, f"Unscramble this "
                                             f"{self.scramble_manager.get_scramble_name(scramble_type)}: "
                                             f"{scrambled_word.lower()}")
        future = self.set_timed_event(120, self.on_scramble_finish, ctx.channel, scramble_type)
        self.scramble_manager.pass_future(scramble_type, ctx.channel, future)

    async def on_scramble(self, ctx, scramble_type):
        money = self.scramble_manager.check_answer(scramble_type, ctx.channel, ctx.message)
        if money is None:
            return
        answer = self.scramble_manager.get_answer(scramble_type, ctx.channel)
        name = self.scramble_manager.get_scramble_name(scramble_type)
        self.scramble_manager.reset(scramble_type, ctx.channel)
        emotes = list(map(lambda e: e.name, self.emotes[ctx.channel]))
        await self.send_message(ctx.channel,
                                f"@{ctx.user.display_name} You got it right! "
                                f"{answer} was the "
                                f"{name}. "
                                f"{'Drake ' if 'Drake' in emotes else ''}"
                                f"You've won {money} Becky Bucks!")
        self.database.add_money(ctx, money)

    @command_manager.command("hint", fargs=["word"])
    @command_manager.command("hint_osu", fargs=["osu"])
    @command_manager.command("hint_map", fargs=["map"])
    @command_manager.command("hint_emote", fargs=["emote"])
    @command_manager.command("hint_genshin", fargs=["genshin"])
    @command_manager.command("hint_anime", fargs=["anime"])
    @command_manager.command("hint_al", fargs=["al"])
    async def hint(self, ctx, scramble_type):
        if not self.scramble_manager.in_progress(scramble_type, ctx.channel):
            return
        if not self.scramble_manager.hints_left(scramble_type, ctx.channel):
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} There are no hints left bruh")
        await self.send_message(ctx.channel,
                                f"Here's a hint "
                                f"({self.scramble_manager.get_scramble_name(scramble_type)}): "
                                f"{self.scramble_manager.get_hint(scramble_type, ctx.channel).lower()}")

    async def on_scramble_finish(self, channel, scramble_type):
        answer = self.scramble_manager.get_answer(scramble_type, channel)
        name = self.scramble_manager.get_scramble_name(scramble_type)
        self.scramble_manager.reset(scramble_type, channel, cancel=False)
        await self.send_message(channel, f"Time is up! The {name} was {answer}")

    @command_manager.command("bal", Cooldown(2, 10), aliases=["balance"])
    async def balance(self, ctx):
        args = ctx.get_args()
        user_to_check = args[0].replace("@", "").lower() if args else None
        if user_to_check is None:
            user_to_check = self.database.get_current_user(ctx).username
        await self.send_message(
            ctx.channel,
            f"{user_to_check} currently has {self.database.get_balance(ctx, user_to_check)} Becky Bucks."
        )

    @command_manager.command("leaderboard", aliases=["lb"])
    async def leaderboard(self, ctx):
        top_users = self.database.get_top_users()
        output = "Top 5 richest users: "
        for i, user in enumerate(top_users):
            output += f'{i + 1}. {user[0]}_${round(user[1])} '
        await self.send_message(ctx.channel, output)

    @command_manager.command("ranking")
    async def get_ranking(self, ctx):
        rank = self.database.get_user_ranking(ctx)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You are currently rank "
                                             f"{rank} in terms of Becky Bucks!")

    @command_manager.command("sheepp_filter", aliases=["sheep_filter"])
    async def filter(self, ctx):
        await self.send_message(
            ctx.channel,
            "Here's a filter that applies to me and any user that uses my commands: https://pastebin.com/nyBX5jbb"
        )

    @command_manager.command("give")
    async def give(self, ctx):
        args = ctx.get_args()
        if len(args) < 2:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must say the user and amount of money to give"
            )
        user_to_give = args[0].lower()
        user = self.database.get_user_from_username(user_to_give)
        if user is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} That user does not exist in the database"
            )
        if not user.receive:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} This user has their receive setting "
                "turned off and therefore cannot accept money."
            )
        amount = args[1]
        try:
            amount = round(int(amount), 2)
        except ValueError:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} That's not a valid number.")

        if amount < 0:
            return await self.send_message(ctx.channel, "You can't give someone a negative amount OuttaPocket Tssk")

        giving_user = self.database.get_current_user(ctx)
        if giving_user.money < amount:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You don't have that much money to give."
            )

        self.database.add_money(ctx, -amount)
        self.database.add_money(self.get_partial_ctx(user.username, user.userid), amount)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} You have given {user.username} {amount} Becky Bucks!"
        )

    @command_manager.command("toggle")
    async def toggle(self, ctx):
        args = ctx.get_args()
        if len(args) < 2:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You must provide a setting name and either on or off"
            )
        setting = args[0].lower()
        if setting not in USER_SETTINGS:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} That's not a valid setting name. "
                f"The settings consist of the following: " +
                ", ".join(USER_SETTINGS)
            )
        try:
            value = {"on": True, "off": False}[args[1].lower()]
        except KeyError:
            return await self.send_message(ctx.channel, "You must specify on or off.")

        self.database.update_userdata(ctx, setting, value)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} The {setting} setting has been turned {args[1]}."
        )

    @command_manager.command("rps", Cooldown(2, 4))
    async def rps(self, ctx):
        args = ctx.get_args()
        if not args:
            return await self.send_message(
                ctx.channel, f"@{ctx.user.display_name} You must say either rock, paper, or scissors. "
                             f"(You can also use the first letter for short)"
            )
        choice = args[0][0].lower()
        if choice not in ('r', 'p', 's'):
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} That's not a valid move. You must say either rock, paper, or scissors. "
                f"(You can also use the first letter for short)"
            )

        com_choice = random.choice(('r', 'p', 's'))
        win = {"r": "s", "s": "p", "p": "r"}
        abbr = {"r": "rock", "s": "scissors", "p": "paper"}
        if com_choice == choice:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} I also chose {abbr[com_choice]}! bruh")
        if win[com_choice] == choice:
            self.database.add_money(ctx, -10)
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} LETSGO I won, {abbr[com_choice]} beats {abbr[choice]}. "
                "You lose 10 Becky Bucks!"
            )
        self.database.add_money(ctx, 10)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} IMDONEMAN I lost, {abbr[choice]} beats {abbr[com_choice]}. "
            "You win 10 Becky Bucks!"
        )
        
    @command_manager.command("new_name", permission=CommandPermission.ADMIN)
    async def new_name(self, ctx):
        args = ctx.get_args()
        if len(args) < 2:
            return await self.send_message(ctx.channel, "Must provide an old and new username")
        old_name = args[0]
        new_name = args[1]
        user = self.database.get_user_from_username(new_name)
        if user is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} New name (second argument) is not valid"
            )
        money = self.database.get_and_delete_old_user(old_name)
        if money is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Old name (first argument) is not valid"
            )
        self.database.add_money(self.get_partial_ctx(user.username, user.userid), money)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Your becky bucks have been transferred!")

    @command_manager.command("scramble_multipliers", aliases=["scramblemultipliers", "scramble_multiplier", "scramblemultiplier"])
    async def scramble_difficulties(self, ctx):
        await self.send_message(ctx.channel,
                                f"@{ctx.user.display_name} Difficulty multiplier for each scramble: "
                                "%s" % ', '.join(
                                    ['%s-%s' % (identifier, scramble.difficulty_multiplier)
                                     for identifier, scramble in self.scrambles.items()])
                                )

    @command_manager.command("scramble_calc", aliases=["scramblecalc"])
    async def scramble_calc(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Scramble payout is calculated by picking a random number 5-10, "
                                             f"multiplying that by the length of the word (excluding spaces), multiplying "
                                             f"that by hint reduction, and multiplying that by the scramble difficulty "
                                             f"multiplier for that specific scramble. To see the difficulty multipliers, "
                                             f"do !scramble_multiplier. Hint reduction is the length of the word minus the "
                                             f"amount of hints used divided by the length of the word.")

    @command_manager.command("afk")
    async def afk(self, ctx):
        args = ctx.get_args()
        message = " ".join(args)
        if ctx.sending_user in self.afks:
            self.database.save_afk(ctx.sending_user, message)
        else:
            self.database.add_afk(ctx.sending_user, message)
        self.afks.append(ctx.sending_user)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Your afk has been set.")

    @command_manager.command("removeafk", aliases=["rafk", "afkremove", "afkr", "unafk"])
    async def afk_remove(self, ctx):
        if ctx.sending_user not in self.afks:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} You are not afk")
        afk = self.database.get_afk(ctx.sending_user)
        await self.remove_user_afk(ctx, afk)

    @command_manager.command("help", aliases=["sheepp_commands", "sheep_commands", "sheepcommands",
                                              "sheeppcommands", "sheephelp", "sheepphelp",
                                              "sheep_help", "sheep_help"])
    async def help_command(self, ctx):
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} sheppsubot help (do !commands for StreamElements): https://bot.sheppsu.me/"
        )

    async def on_afk(self, ctx):
        pings = set([word.replace("@", "").replace(",", "").replace(".", "").replace("-", "") for word in ctx.message.lower().split() if word.startswith("@")])
        for ping in pings:
            if ping in self.afks:
                afk = self.database.get_afk(ping)
                await self.send_message(
                    ctx.channel,
                    f"@{ctx.user.display_name} {ping} is afk ({format_date(afk.time)} ago): {afk.message}"
                )

        if ctx.sending_user not in self.afks:
            return
        user = self.database.get_current_user(ctx)
        if not user.autoafk:
            return
        afk = self.database.get_afk(ctx.sending_user)
        if afk is None:
            self.afks.remove(ctx.sending_user)
            return
        if (datetime.now(tz=tz.utc) - afk.time.replace(tzinfo=tz.utc)).seconds > 60:
            await self.remove_user_afk(ctx, afk)

    async def remove_user_afk(self, ctx, afk):
        self.afks.remove(ctx.sending_user)
        self.database.delete_afk(ctx.user.username)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Your afk has been removed. "
            f"(Afk for {format_date(afk.time)}.)"
        )

    async def trivia_category(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} I'll make something more intuitive later but for now, "
                                             f"if you want to know which number correlates to which category, "
                                             f"go here https://opentdb.com/api_config.php, click a category, "
                                             f"click generate url and then check the category specified in the url.")

    @command_manager.command("sourcecode", aliases=["sheepcode", "sheeppcode", "sheep_code", "sheepp_code"])
    async def sourcecode(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} https://github.com/Sheepposu/offlinechatbot")

    # Bomb party functions
    @command_manager.command("bombparty", aliases=["bomb_party"])
    async def bomb_party(self, ctx):
        if self.bomb_party_helper.in_progress:
            return
        self.bomb_party_helper.add_player(ctx.user.username)
        self.bomb_party_helper.on_in_progress()

        await self.send_message(ctx.channel, f"{ctx.user.username} has started a Bomb Party game! Anyone else who wants to play should type !join. When enough players have joined, the host should type !start to start the game, otherwise the game will automatically start or close after 2 minutes.")
        self.bomb_party_future = self.set_timed_event(120, self.close_or_start_game, ctx.channel)

    async def close_or_start_game(self, channel):
        if not self.bomb_party_helper.can_start:
            self.bomb_party_helper.on_close()
            return await self.send_message(channel, "The bomb party game has closed since there is only one player in the party.")
        await self.start_bomb_party(MessageContext("", channel), True)

    @command_manager.command("start")
    async def start_bomb_party(self, ctx, auto=False):
        if not auto and (not self.bomb_party_helper.in_progress or
                         self.bomb_party_helper.started or
                         ctx.user.username != self.bomb_party_helper.host):
            return
        if not self.bomb_party_helper.can_start:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} You need at least 2 players to start the bomb party game.")
        if not auto:
            self.bomb_party_future.cancel()

        self.bomb_party_helper.on_start()
        self.bomb_party_helper.set_letters()

        await self.send_message(ctx.channel, f"@{self.bomb_party_helper.current_player} You're up first! Your string of letters is {self.bomb_party_helper.current_letters}")
        self.bomb_party_future = self.set_timed_event(self.bomb_party_helper.starting_time, self.bomb_party_timer, ctx.channel)

    @command_manager.command("join", Cooldown(0, 3))
    async def join_bomb_party(self, ctx):
        if not self.bomb_party_helper.in_progress or self.bomb_party_helper.started:
            return
        if ctx.user.username in self.bomb_party_helper.party:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} You have already joined the game")

        self.bomb_party_helper.add_player(ctx.user.username)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You have joined the game of bomb party!")

    @command_manager.command("leave", Cooldown(0, 3))
    async def leave_bomb_party(self, ctx):
        if ctx.user.username not in self.bomb_party_helper.party:
            return
        self.bomb_party_helper.remove_player(ctx.user.username)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You have left the game of bomb party.")
        if self.bomb_party_helper.started and await self.check_win(ctx.channel):
            if self.bomb_party_future is not None:
                self.bomb_party_future.cancel()  #
        elif self.bomb_party_helper.started and self.bomb_party_helper.current_player.user == ctx.user.username:
            if self.bomb_party_future is not None:
                self.bomb_party_future.cancel()
            await self.next_player(ctx.channel)
        elif self.bomb_party_helper.in_progress and not self.bomb_party_helper.started:
            if len(self.bomb_party_helper.party) == 0:
                self.close_bomb_party()
                await self.send_message(ctx.channel, "The game of bomb party has closed.")

    @command_manager.command("settings", Cooldown(0, 0))
    async def change_bomb_settings(self, ctx):
        if not self.bomb_party_helper.in_progress or \
                self.bomb_party_helper.started or \
                self.bomb_party_helper.host != ctx.user.username:
            return
        args = ctx.get_args("ascii")
        if len(args) < 2:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} You must provide a setting name and the value: "
                                                        f"!settings <setting> <value>. Valid settings: "
                                                        f"{self.bomb_party_helper.valid_settings_string}")
        setting = args[0]
        value = args[1]
        return_msg = self.bomb_party_helper.set_setting(setting, value)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} {return_msg}")

    @command_manager.command("players")
    async def player_list(self, ctx):
        if not self.bomb_party_helper.in_progress:
            return
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Current players playing bomb party: {', '.join(self.bomb_party_helper.player_list)}")

    async def bomb_party_timer(self, channel):
        self.exploding = True
        msg = self.bomb_party_helper.on_explode()
        print(msg)
        await self.send_message(channel, msg)
        print("checking win")
        if await self.check_win(channel):
            return
        print("next player")
        self.exploding = False
        await self.next_player(channel)

    async def next_player(self, channel):
        self.bomb_party_helper.next_player()
        self.bomb_party_helper.set_letters()
        player = self.bomb_party_helper.current_player
        await self.send_message(channel, f"@{player} Your string of letters is {self.bomb_party_helper.current_letters} - "
                                         f"You have {round(self.bomb_party_helper.seconds_left)} seconds.")
        self.bomb_party_future = self.set_timed_event(self.bomb_party_helper.seconds_left, self.bomb_party_timer, channel)

    async def on_bomb_party(self, ctx):
        word = ctx.message.lower()
        if ctx.user.username != self.bomb_party_helper.current_player.user:
            return
        if word not in self.all_words:
            return
        return_msg = self.bomb_party_helper.check_message(word)
        if return_msg is not None:
            return await self.send_message(ctx.channel, f"@{self.bomb_party_helper.current_player} {return_msg}")
        if self.exploding:
            return
        self.bomb_party_future.cancel()
        self.bomb_party_helper.on_word_used(word)
        await self.next_player(ctx.channel)

    async def check_win(self, channel):
        winner = self.bomb_party_helper.get_winner()
        if winner is None:
            return False
        winner = winner.user
        money = self.bomb_party_helper.winning_money
        user = self.database.get_user_from_username(winner)
        # yep you're reading this right
        # if you don't already exist in the database you get no becky bucks!
        # why? I need the user's userid and I'm too lazy to fix that problem rn
        if user is not None:
            self.database.add_money(self.get_partial_ctx(user.username, user.userid), money)
        self.close_bomb_party(False)
        await self.send_message(channel, f"@{winner} Congratulations on winning the bomb party game! You've won {money} Becky Bucks!")
        return True

    def close_bomb_party(self, cancel=True):
        if cancel and not self.bomb_party_future.done():
            self.bomb_party_future.cancel()
        self.bomb_party_future = None
        self.bomb_party_helper.on_close()

    @command_manager.command("funfact")
    async def random_fact(self, ctx):
        fact = requests.get("https://uselessfacts.jsph.pl/random.json?language=en")
        fact.raise_for_status()
        await self.send_message(ctx.channel, f"Fun fact: {fact.json()['text']}")

    @command_manager.command("anime_compare", aliases=["animecompare", "ac"], cooldown=Cooldown(0, 5),
                             banned=["osuwho"])
    async def anime_compare(self, ctx):
        game = self.compare_helper.get_game(ctx.user.username)
        if game is not None:
            return
        game = self.compare_helper.new_game(ctx.user.username, self.anime)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} {game.get_question_string()}")
        game.id = self.database.new_animecompare_game(ctx.user.username)
        self.anime_compare_future[ctx.user.username] = self.set_timed_event(10, self.anime_compare_timeout, ctx, game)

    async def on_anime_compare(self, ctx, game):
        check = self.compare_helper.check_guess(ctx, game)
        if check is None:
            return
        self.anime_compare_future[ctx.user.username].cancel()
        self.anime_compare_future[ctx.user.username] = None
        if not check:
            await self.send_message(ctx.channel, f"@{ctx.user.display_name} Incorrect. Your final score is {game.score}. {game.get_ranking_string()}.")
            self.database.finish_animecompare_game(game.id)
            self.compare_helper.finish_game(game)
        else:
            await self.send_message(ctx.channel, f"@{ctx.user.display_name} Correct! Your current score is {game.score}. {game.get_ranking_string()}.")
            self.compare_helper.generate_answer(self.anime, game)
            self.database.update_animecompare_game(game.id, game.score)
            await self.send_message(ctx.channel, f"@{ctx.user.display_name} {game.get_question_string()}")
            self.anime_compare_future[ctx.user.username] = self.set_timed_event(10, self.anime_compare_timeout, ctx, game)

    async def anime_compare_timeout(self, ctx, game):
        self.compare_helper.finish_game(game)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You did not answer in time. Your final score is {game.score}.")
        self.database.finish_animecompare_game(game.id)
        self.anime_compare_future[ctx.user.username] = None

    @command_manager.command("average_ac", aliases=["acaverage", "ac_avg", "ac_average", "acavg"])
    async def average_anime_compare(self, ctx):
        avg_score = self.database.get_ac_user_average(ctx.sending_user)
        if avg_score is not None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Your average score is {avg_score}.")
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You have not played any anime compare games")

    @command_manager.command("ac_leaderboard", aliases=["aclb", "ac_lb", "acleaderboard"])
    async def anime_compare_leaderboard(self, ctx):
        games = self.database.get_top_animecompare_games()
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} The top anime compare scores are: {', '.join(['%s_%d' %(game['user'], game['score']) for game in games])}.")

    @command_manager.command("ac_top", aliases=["actop", "topac", "top_ac"], cooldown=Cooldown(0, 5))
    async def anime_compare_top(self, ctx):
        game = self.database.get_top_animecompare_game_for_user(ctx.user.username)
        if not game:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} You have not played any anime compare games yet.")
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Your top anime compare score is {game[0]['score']}.")

    def process_value_arg(self, flag, args, default=None):
        lower_args = list(map(str.lower, args))
        if flag in lower_args:
            index = lower_args.index(flag)
            args.pop(index)
            if len(args) == 0:
                return
            value = args.pop(index).strip()
            return value
        return default

    def process_arg(self, flag, args):
        lower_args = list(map(str.lower, args))
        if flag in lower_args:
            args.pop(lower_args.index(flag))
            return True
        return False

    async def process_osu_user_arg(self, ctx, args):
        if len(args) > 0:
            return " ".join(args).strip()
        osu_user = self.database.get_osu_user_from_username(ctx.sending_user)
        if osu_user is not None:
            self.osu_user_id_cache[osu_user[1]] = osu_user[0]
            return osu_user[0]
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Please specify a username or link your account with !link [username]."
        )

    async def process_osu_mode_args(self, ctx, args):
        arg = self.process_value_arg("-m", args, 0)
        if arg is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Must specify a mode with the -m argument. "
                                                        f"Valid modes are 0 (osu), 1 (taiko), 2 (catch), 3 (mania).")
        if type(arg) != int and (not arg.isdigit() or int(arg) not in range(0, 4)):
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Invalid mode. Valid modes "
                                                        f"are 0 (osu), 1 (taiko), 2 (catch), 3 (mania).")
        return ("osu", "taiko", "fruits", "mania")[int(arg)]

    async def process_index_arg(self, ctx, args, rng=range(1, 101)):
        arg = self.process_value_arg("-i", args, -1)
        if arg == -1:
            return -1
        if arg is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Must specify an index with the -i argument. "
                                                        f"Specify a number between {rng[0]} and {rng[-1]}")
        if arg.lower() == "random":
            return random.choice(rng)-1
        if type(arg) != int and (not arg.isdigit() or int(arg) not in rng):
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Must specify a number between "
                                                        f"{rng[0]} and {rng[-1]} for the -i argument.")
        return int(arg)-1

    async def get_osu_user_id_from_osu_username(self, ctx, username):
        if username not in self.osu_user_id_cache:
            user = await self.make_osu_request(self.osu_client.get_user(user=username, key="username"))
            if user is None:
                await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")
                return
            self.osu_user_id_cache[username] = user.id
        return self.osu_user_id_cache[username]

    @staticmethod
    def get_if_fc(o_score, beatmap, beatmap_attributes):
        score = deepcopy(o_score)
        if score.ruleset_id == GameModeInt.STANDARD.value:
            count_300 = score.statistics.great if score.statistics.great else 0
            count_100 = score.statistics.ok if score.statistics.ok else 0
            count_50 = score.statistics.meh if score.statistics.meh else 0
            count_miss = score.statistics.miss if score.statistics.miss else 0
            total_objects = beatmap.count_sliders + beatmap.count_spinners + beatmap.count_circles
            total_hits = count_300 + count_100 + count_50 + count_miss

            count_300 += count_miss + total_objects - total_hits
            score.statistics.great = count_300
            score.statistics.miss, count_miss = 0, 0
            score.max_combo = beatmap_attributes.max_combo

            accuracy = (count_300 * 300 + count_100 * 100 + count_50 * 50) / \
                       (300 * (count_300 + count_100 + count_50 + count_miss))
            score.accuracy = accuracy

            return accuracy, Bot.calculate_pp(score, beatmap, beatmap_attributes)

    @staticmethod
    def calculate_pp(score, beatmap, beatmap_attributes, transform=True):
        if beatmap.mode == GameModeStr.STANDARD:
            attributes = OsuDifficultyAttributes.from_attributes({
                'aim_difficulty': beatmap_attributes.mode_attributes.aim_difficulty,
                'speed_difficulty': beatmap_attributes.mode_attributes.speed_difficulty,
                'flashlight_difficulty': beatmap_attributes.mode_attributes.flashlight_difficulty,
                'slider_factor': beatmap_attributes.mode_attributes.slider_factor,
                'speed_note_count': beatmap_attributes.mode_attributes.speed_note_count,
                'approach_rate': beatmap_attributes.mode_attributes.approach_rate,
                'overall_difficulty': beatmap_attributes.mode_attributes.overall_difficulty,
                'max_combo': beatmap_attributes.max_combo,
                'drain_rate': beatmap.drain,
                'hit_circle_count': beatmap.count_circles,
                'slider_count': beatmap.count_sliders,
                'spinner_count': beatmap.count_spinners,
            })
            if transform:
                # temporary solution until pp calc accepts other mods
                all_mods = score.mods
                limited_mods = list(filter(lambda m: type(m.mod) != str and m.mod.name in Mods._member_names_, score.mods))
                if len(limited_mods) != len(all_mods):
                    return
                score.mods = limited_mods
                score_attributes = OsuScoreAttributes.from_osupy_score(score)
                score.mods = all_mods
            else:
                score_attributes = score
            calculator = OsuPerformanceCalculator(GameModeStr.STANDARD, attributes, score_attributes)
            try:
                return calculator.calculate()
            except:
                traceback.print_exc()

    @staticmethod
    def get_hit_data(statistics, ruleset_id):
        if isinstance(statistics, ScoreDataStatistics):
            if ruleset_id == GameModeInt.STANDARD.value:
                hit_string = "%d/%d/%d/%d" % (hits := (
                    statistics.great or 0,
                    statistics.ok or 0,
                    statistics.meh or 0,
                    statistics.miss or 0
                ))
            else:
                hit_string = "%d/%d/%d/%d/%d/%d" % (hits := (
                    statistics.perfect or 0,
                    statistics.great or 0,
                    statistics.good or 0,
                    statistics.ok or 0,
                    statistics.meh or 0,
                    statistics.miss or 0
                ))
        else:
            if ruleset_id == GameModeInt.STANDARD.value:
                hit_string = "%d/%d/%d/%d" % (hits := (
                    statistics.count_300,
                    statistics.count_100,
                    statistics.count_50,
                    statistics.count_miss
                ))
            else:
                hit_string = "%d/%d/%d/%d/%d/%d" % (hits := (
                    statistics.count_geki,
                    statistics.count_300,
                    statistics.count_katu,
                    statistics.count_100,
                    statistics.count_50,
                    statistics.count_miss
                ))
        return hit_string, sum(hits)

    def get_score_message(self, score, beatmap, beatmap_attributes, prefix="Recent score for {username}"):
        score_format = prefix+":{passed} {artist} - {title} [{diff}]{mods} ({mapper}, {star_rating}*) " \
                    "{acc}% {combo}/{max_combo} | ({genki_counts}) | {pp}{if_fc_pp} | {time_ago} ago"
        # Format and send message for recent score
        hit_string, total_hits = self.get_hit_data(score.statistics, self.parse_score_mode_int(score))
        total_objects = beatmap.count_sliders + beatmap.count_spinners + beatmap.count_circles
        if score.pp is None and score.passed and score.ruleset_id == GameModeInt.STANDARD.value and beatmap_attributes.type is not None:
            score.pp = self.calculate_pp(score, beatmap, beatmap_attributes)
        if_fc_acc, if_fc_pp = None, None
        if beatmap_attributes.type is not None and score.max_combo != beatmap_attributes.max_combo and score.ruleset_id == GameModeInt.STANDARD.value:
            if_fc_acc, if_fc_pp = self.get_if_fc(score, beatmap, beatmap_attributes)
        return score_format.format(**{
            "username": score.user.username,
            "passed": "" if score.passed else f" (Failed {round(total_hits / total_objects * 100)}%)",
            "artist": beatmap.beatmapset.artist,
            "title": beatmap.beatmapset.title,
            "diff": beatmap.version,
            "mods": " +" + "".join(map(lambda m: m.mod.value, score.mods)) if score.mods else "",
            "mapper": beatmap.beatmapset.creator,
            "star_rating": round(beatmap_attributes.star_rating, 2),
            "pp": f"{round(score.pp, 2)}pp" if score.pp and score.passed else "",
            "if_fc_pp": f" ({round(if_fc_pp, 2)} for {round(if_fc_acc * 100, 2)}% FC)" if if_fc_pp is not None else "",
            "acc": round(score.accuracy * 100, 2),
            "combo": score.max_combo,
            "max_combo": beatmap_attributes.max_combo,
            "genki_counts": hit_string,
            "time_ago": format_date(score.ended_at)
        })

    async def get_compact_scores_message(self, scores):
        score_format = "{artist} - {title} [{diff}]{mods} {acc}% ({genki_counts}): {pp}pp | {time_ago} ago"
        message = ""
        beatmap_ids = list(map(lambda s: s.beatmap_id, scores))
        beatmaps = sorted(
            await self.make_osu_request(self.osu_client.get_beatmaps(beatmap_ids)), key=lambda b: beatmap_ids.index(b.id)
        )
        for i, score in enumerate(scores):
            hit_string, _ = self.get_hit_data(score.statistics, score.ruleset_id)
            beatmap = beatmaps[i]
            message += "🌟" + score_format.format(**{
                "artist": beatmap.beatmapset.artist,
                "title": beatmap.beatmapset.title,
                "diff": beatmap.version,
                "mods": " +" + "".join(map(lambda m: m.mod.value, score.mods)) if score.mods else "",
                "acc": round(score.accuracy * 100, 2),
                "genki_counts": hit_string,
                "pp": 0 if score.pp is None else round(score.pp, 2),
                "time_ago": format_date(score.ended_at),
            })
        return message

    async def get_osu_user_id_from_args(self, ctx, args):
        user = await self.process_osu_user_arg(ctx, args)
        if user is None:
            return
        if type(user) == str:
            return await self.get_osu_user_id_from_osu_username(ctx, user)
        return user

    def osu_username_from_id(self, user_id):
        for username, osu_user_id in self.osu_user_id_cache.items():
            if osu_user_id == user_id:
                return username

    async def make_osu_request(self, request, use_lazer=False):
        await self.osu_lock.acquire()
        self.osu_client.http.use_lazer = use_lazer
        try:
            result = await request
        except:
            traceback.print_exc()
            result = None
        self.osu_lock.release()
        return result

    def get_map_cache(self, ctx):
        if len(self.recent_score_cache[ctx.channel]) == 0:
            return
        if ctx.reply:
            if ctx.reply.msg_body in self.recent_score_cache[ctx.channel]:
                return self.recent_score_cache[ctx.channel][ctx.reply.msg_body]
            return
        return list(self.recent_score_cache[ctx.channel].values())[-1]

    def add_recent_map(self, ctx, sent_message, beatmap, attributes):
        msg = " ".join(sent_message)
        if msg in self.recent_score_cache[ctx.channel]:
            del self.recent_score_cache[ctx.channel][msg]
        self.recent_score_cache[ctx.channel].update({msg: (beatmap, attributes)})
        while len(self.recent_score_cache) > 50:
            del self.recent_score_cache[ctx.channel][list(self.recent_score_cache[ctx.channel].keys())[0]]

    async def get_beatmap_from_arg(self, ctx, beatmap_link):
        beatmap_id = tuple(filter(lambda s: len(s.strip()) > 0, beatmap_link.split("/")))[-1]
        beatmap = await self.make_osu_request(self.osu_client.get_beatmap(beatmap_id))
        if beatmap is None:
            return await self.send_message(ctx.channel, "Failed to get beatmap from the provided link/id.")
        beatmap_attributes = await self.make_osu_request(self.osu_client.get_beatmap_attributes(beatmap_id))
        return beatmap, beatmap_attributes

    @staticmethod
    def parse_score_mods(score):
        if isinstance(score, SoloScore):
            # temporary thing until I fix some libraries
            return list(map(lambda m: m.mod.value, filter(lambda m: type(m.mod) != str and m.mod.name in Mods._member_names_, score.mods))) if score.mods else None
        return score.mods

    @staticmethod
    def parse_score_mode_int(score):
        if isinstance(score, SoloScore):
            return score.ruleset_id
        return score.mode_int.value

    @command_manager.command("rs", cooldown=Cooldown(0, 3))
    async def recent_score(self, ctx):
        args = ctx.get_args('ascii')
        mode = await self.process_osu_mode_args(ctx, args)
        if mode is None:
            return
        index = await self.process_index_arg(ctx, args)
        if index is None:
            return
        if index == -1:
            index = 0
        best = self.process_arg("-b", args)

        user_id = await self.get_osu_user_id_from_args(ctx, args)
        if user_id is None:
            return
        username = self.osu_username_from_id(user_id)

        # Get recent score
        if not best:
            scores = await self.make_osu_request(
                self.osu_client.get_user_scores(
                    user_id, "recent", include_fails=1, mode=mode, limit=1, offset=index))
        else:
            scores = await self.make_osu_request(
                self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=100))
            scores = sorted(scores, key=lambda x: x.ended_at, reverse=True)
        if not scores:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} "
                                                        f"has no recent scores for {proper_mode_name[mode]} "
                                                        "or the index you specified is out of range.")

        score = scores[0 if not best else index]
        if isinstance(score, SoloScore):
            beatmap = await self.make_osu_request(
                self.osu_client.get_beatmap(score.beatmap_id))
        else:
            beatmap = score.beatmap
        beatmap_attributes = await self.make_osu_request(
            self.osu_client.get_beatmap_attributes(beatmap.id, self.parse_score_mods(score), ruleset_id=self.parse_score_mode_int(score)))
        sent_message = await self.send_message(ctx.channel, self.get_score_message(score, beatmap, beatmap_attributes))
        self.add_recent_map(ctx, sent_message, beatmap, beatmap_attributes)

    @command_manager.command("c", aliases=['compare'], cooldown=Cooldown(0, 3))
    async def compare_score(self, ctx):
        if not len(self.recent_score_cache[ctx.channel]):
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} I don't have a cache of the last beatmap.")
        cache = self.get_map_cache(ctx)
        if cache is None: return
        await self.compare_score_func(ctx, False, cache)

    async def compare_score_func(self, ctx, most_recent=True, cache=None):
        beatmap, beatmap_attributes = list(self.recent_score_cache[ctx.channel].values())[-1] if most_recent else cache
        args = ctx.get_args('ascii')
        if '-m' not in map(str.lower, args):
            mode = None
        else:
            mode = await self.process_osu_mode_args(ctx, args)
            if mode is None:
                return

        user_id = await self.get_osu_user_id_from_args(ctx, args)
        if user_id is None:
            return
        username = self.osu_username_from_id(user_id)

        update_beatmap_attributes = mode is not None and mode != beatmap.mode.value
        if mode is None:
            mode = beatmap.mode.value

        try:
            scores = await self.make_osu_request(
                self.osu_client.get_user_beatmap_scores(beatmap.id, user_id, mode))
        except client_exceptions.ClientResponseError:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} This map does not have a leaderboard.")
        if not scores:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} has no "
                                                        f"scores on that beatmap for mode {proper_mode_name[mode]}.")

        # For max_combo attribute
        if update_beatmap_attributes:
            beatmap_attributes = await self.make_osu_request(self.osu_client.get_beatmap_attributes(beatmap.id, ruleset=mode))

        score_format = "{mods} {acc}% {combo}/{max_combo} | ({genki_counts}) | {pp} | {time_ago} ago"
        message = f"Scores for {username} on {beatmap.beatmapset.artist} - {beatmap.beatmapset.title} " \
                  f"[{beatmap.version}] ({beatmap.beatmapset.creator}): "
        for score in scores[:5]:
            hit_string, _ = self.get_hit_data(score.statistics, score.ruleset_id)
            message += "🌟" + score_format.format(**{
                "mods": " +" + "".join(map(lambda m: m.mod.value, score.mods)) if score.mods else "",
                "acc": round(score.accuracy * 100, 2),
                "combo": score.max_combo,
                "max_combo": beatmap_attributes.max_combo,
                "genki_counts": hit_string,
                "pp": f"{round(score.pp, 2)}pp" if score.pp else "No pp",
                "time_ago": format_date(score.ended_at)
            })
        sent_message = await self.send_message(ctx.channel, message)
        self.add_recent_map(ctx, sent_message, beatmap, beatmap_attributes)

    @command_manager.command("map", aliases=["m"])
    async def send_map(self, ctx):
        args = ctx.get_args('ascii')
        if len(args) > 0:
            result = await self.get_beatmap_from_arg(ctx, args[0])
            if result is None:
                return
            beatmap, beatmap_attributes = result
        elif len(self.recent_score_cache[ctx.channel]) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} I don't have a cache of the last beatmap.")
        else:
            beatmap, beatmap_attributes = self.get_map_cache(ctx)
            # TODO: make less scuffed lole
            beatmap_attributes = await self.make_osu_request(self.osu_client.get_beatmap_attributes(beatmap.id, ruleset=beatmap.mode))

        if beatmap is None or beatmap_attributes is None: return

        text = f"{beatmap.beatmapset.artist} - {beatmap.beatmapset.title} [{beatmap.version}] " \
               f"({beatmap.beatmapset.creator}, {round(beatmap_attributes.star_rating, 2)}*) https://osu.ppy.sh/b/{beatmap.id}"
        sent_message = await self.send_message(ctx.channel, f"@{ctx.user.display_name} {text}")
        self.add_recent_map(ctx, sent_message, beatmap, beatmap_attributes)

    @command_manager.command("osu", cooldown=Cooldown(0, 5))
    async def osu_profile(self, ctx):
        args = ctx.get_args('ascii')
        use_lazer = self.process_arg('-l', args)
        mode = await self.process_osu_mode_args(ctx, args)
        if mode is None:
            return
        user = await self.get_osu_user_id_from_args(ctx, args)
        if user is None:
            return
        username = self.osu_username_from_id(user)

        try:
            user = await self.make_osu_request(
                self.osu_client.get_user(user=user, mode=mode, key="username" if type(user) == str else "id"), use_lazer)
        except client_exceptions.ClientResponseError:
            return await self.send_message(ctx.channel, f"{ctx.user.display_name} A user with the name {username} "
                                                        "does not exist. If they did before it's possible they "
                                                        "got restricted or had their account deleted.")

        if user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")

        stats = user.statistics

        total_medals = 280
        profile_layout = "{username}'s profile [{mode}]: #{global_rank} ({country}#{country_rank}) - {pp}pp; Peak: #{peak_rank} {peak_time_ago} ago | " \
                         "{accuracy}% | {play_count} playcount ({play_time} hrs) | Medal count: {medal_count}/{total_medals} ({medal_completion}%) | " \
                         "Followers: {follower_count} | Mapping subs: {subscriber_count}"
        await self.send_message(ctx.channel, profile_layout.format(**{
            "username": user.username,
            "mode": proper_mode_name[mode],
            "global_rank": stats.global_rank,
            "country": user.country.code,
            "country_rank": stats.country_rank,
            "pp": stats.pp,
            "peak_rank": user.rank_highest.rank,
            "peak_time_ago": format_date(user.rank_highest.updated_at),
            "accuracy": round(stats.hit_accuracy, 2),
            "play_count": stats.play_count,
            "play_time": stats.play_time//3600,
            "medal_count": len(user.user_achievements),
            "total_medals": total_medals,
            "medal_completion": round(len(user.user_achievements) / total_medals * 100, 2),
            "follower_count": user.follower_count,
            "subscriber_count": user.mapping_follower_count,
        }))

    @command_manager.command("osutop", cooldown=Cooldown(0, 5))
    async def osu_top(self, ctx):
        args = ctx.get_args('ascii')

        use_lazer = self.process_arg('-l', args)
        mode = await self.process_osu_mode_args(ctx, args)
        if mode is None:
            return
        recent_tops = self.process_arg("-r", args)
        index = await self.process_index_arg(ctx, args)
        if index is None:
            return

        user_id = await self.get_osu_user_id_from_args(ctx, args)
        if user_id is None:
            return
        username = self.osu_username_from_id(user_id)

        top_scores = await self.make_osu_request(
            self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=100), use_lazer)
        if not top_scores:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} User {username} has no top scores for {proper_mode_name[mode]}."
            )
        if recent_tops:
            top_scores = sorted(top_scores, key=lambda x: x.ended_at, reverse=True)
        top_scores = top_scores[:5] if index == -1 else [top_scores[index]]
        username = top_scores[0].user.username

        beatmap = None
        beatmap_attributes = None
        if len(top_scores) > 1:
            message = f"Top{' recent' if recent_tops else ''} {proper_mode_name[mode]} " \
                      f"scores for {username}: " if index == -1 else f"Top {index+1}{' recent' if recent_tops else ''} " \
                                                                     f"{proper_mode_name[mode]} score for {username}: "
            message += await self.get_compact_scores_message(top_scores)
        else:
            score = top_scores[0]
            beatmap = await self.make_osu_request(self.osu_client.get_beatmap(score.beatmap_id))
            beatmap_attributes = await self.make_osu_request(
                self.osu_client.get_beatmap_attributes(
                    beatmap.id,
                    self.parse_score_mods(score),
                    ruleset_id=self.parse_score_mode_int(score)
                )
            )
            message = self.get_score_message(score, beatmap, beatmap_attributes,
                                             prefix=f"Top {index+1}{' recent' if recent_tops else ''} score for {username}")

        sent_message = await self.send_message(ctx.channel, message)
        if beatmap_attributes is not None:
            self.add_recent_map(ctx, sent_message, beatmap, beatmap_attributes)

    @command_manager.command("link", cooldown=Cooldown(0, 2))
    async def link_osu_account(self, ctx):
        args = ctx.get_args('ascii')
        if len(args) == 0 or args[0].strip() == "":
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Please specify a username.")

        username = " ".join(args).strip()
        user = await self.make_osu_request(
            self.osu_client.get_user(user=username, key="username"))

        if user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")

        osu_user = self.database.get_osu_user_from_username(ctx.sending_user)
        if osu_user is not None:
            self.database.update_osu_data(ctx.user.username, user.username, user.id)
        else:
            self.database.new_osu_data(ctx.user.username, user.username, user.id)
        self.osu_user_id_cache[user.username] = user.id

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Linked {user.username} to your account.")

    @command_manager.command("simulate", cooldown=Cooldown(0, 2), aliases=["s"])
    async def simulate_score(self, ctx):
        if len(self.recent_score_cache[ctx.channel]) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} I don't have a cache of the last beatmap.")
        beatmap = self.get_map_cache(ctx)
        if beatmap is None: return
        beatmap = beatmap[0]
        if beatmap.mode != GameModeStr.STANDARD:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Sorry, but I only support pp calculation for osu!std at the moment.")

        args = ctx.get_args("ascii")
        if len(args) == 0:
            mods = None
        else:
            mods = args[0]
            if mods.startswith("+"):
                mods = mods[1:]
            mods = [mods[i*2:i*2+2] for i in range(len(mods)//2)]
            try:
                mods = list(map(Mods.get_from_abbreviation, mods))
            except KeyError:
                return await self.send_message(ctx.channel, f"{ctx.user.display_name} The mod combination you gave is invalid.")
            mods = Mods.get_from_list(mods)

        beatmap_difficulty = await self.make_osu_request(
            self.osu_client.get_beatmap_attributes(beatmap.id, mods))

        pp_values = []
        total_objects = beatmap.count_sliders + beatmap.count_circles + beatmap.count_spinners
        for acc in (1, 0.99, 0.98, 0.97, 0.96, 0.95):
            h2 = round((3/2)*total_objects*(1-acc))
            h1 = total_objects - h2
            actual_acc = (300*h1 + 100*h2)/(300*total_objects)
            score = OsuScoreAttributes()
            score.set_attributes({
                "mods": mods,
                "accuracy": actual_acc,
                "score_max_combo": beatmap_difficulty.max_combo,
                "count_great": h1,
                "count_ok": h2,
                "count_meh": 0,
                "count_miss": 0,
            })
            pp = self.calculate_pp(score, beatmap, beatmap_difficulty, False)
            pp_values.append(f"{int(acc*100)}% - {round(pp, 2)}")

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} {beatmap.beatmapset.artist} - "
                                             f"{beatmap.beatmapset.title} [{beatmap.version}] "
                                             f"{mods.to_readable_string() if mods is not None else 'NM'}: "
                                             f"{' | '.join(pp_values)}")

    @command_manager.command("score", aliases=["sc"])
    async def osu_score(self, ctx):
        args = ctx.get_args('ascii')

        if len(args) < 1:
            return await self.send_message(ctx.channel, "Must give a beatmap link or beatmap id.")
        result = await self.get_beatmap_from_arg(ctx, args[0])
        if result is None:
            return
        beatmap, beatmap_attributes = result

        i = ctx.message.index(args[0])
        ctx.message = (ctx.message[:i] + ctx.message[i+len(args[0])+1:]).strip()

        await self.compare_score_func(ctx, False, (beatmap, beatmap_attributes))
        
    @command_manager.command("send_map", aliases=["sm"])
    async def send_osu_map(self, ctx):
        beatmap = self.get_map_cache(ctx)
        if beatmap is None: return
        osu_user = self.database.get_osu_user_from_username(ctx.sending_user)
        if osu_user is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You must have your osu account linked and verified to use this command. "
                "You can link and verify by logging in at https://bot.sheppsu.me and "
                "then going to https://bot.sheppsu.me/osuauth (will take a few minutes to update)"
            )
        if not int(osu_user[2]):
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You must have a verified account link to use this command. "
                "Go to https://bot.sheppsu.me, login, and then go to https://bot.sheppsu.me/osuauth (will take a few minutes to update)"
            )
        
        beatmap = beatmap[0]
        bms = beatmap.beatmapset
        bms_title = f"{bms.artist} - {bms.title} [{beatmap.version}] mapped by {bms.creator}"
        await self.make_osu_request(self.osu_client.create_new_pm(osu_user[0], f"(Automated bot message) [{bms_title}](https://osu.ppy.sh/b/{beatmap.id})", False))
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Sent the beatmap to your osu DMs!")

    @command_manager.command("preview", aliases=["p"])
    async def send_osu_preview(self, ctx):
        cache = self.get_map_cache(ctx)
        if cache is None:
            return
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} https://preview.tryz.id.vn/?b={cache[0].id}")

    @command_manager.command("validtz")
    async def valid_timezones(self, ctx):
        await self.send_message(ctx.channel, "Having trouble linking your timezone? Here's a list of valid timezones (use the text on the left column): "
                                "https://www.ibm.com/docs/en/cloudpakw3700/2.3.0.0?topic=SS6PD2_2.3.0/doc/psapsys_restapi/time_zone_list.html")

    @command_manager.command("linktz", cooldown=Cooldown(0, 3))
    async def link_timezone(self, ctx):
        args = ctx.get_args("ascii")
        if len(args) == 0 or args[0].strip() == "":
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Please specify a timezone to link.")

        tz = args[0].lower().strip()
        lower_timezones = list(map(str.lower, all_timezones))
        if tz not in lower_timezones:
            if tz.upper() in self.tz_abbreviations:
                tz = self.tz_abbreviations[tz.upper()][0]
            else:
                return await self.send_message(
                    ctx.channel,
                    f"@{ctx.user.display_name} That's not a valid timezone. "
                    "For setting the tz by UTC or GMT, as an examples: UTC+5 would be Etc/GMT-5. "
                    "Do !validtz if you are having trouble."
                )
        else:
            tz = all_timezones[lower_timezones.index(tz)]

        timezone = self.database.get_user_timezone(ctx.user_id)
        if timezone:
            self.database.update_timezone(ctx.user_id, tz)
        else:
            self.database.add_timezone(ctx.user_id, tz)

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Timezone has been linked!")

    @command_manager.command("utime", aliases=["usertime"], cooldown=Cooldown(1, 1))
    async def user_time(self, ctx):
        args = ctx.get_args("ascii")
        if len(args) == 0 or args[0].strip() == "":
            username = ctx.user.username
        else:
            username = args[0].lower().replace("@", "")

        user = self.database.get_user_from_username(username)
        if user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} {username} is not in the database")
        tz = self.database.get_user_timezone(user.userid)
        if tz is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} "
                                                        f"{'This user has' if username != ctx.user.username else 'You have'} "
                                                        f"not linked a timezone, which can be done with !linktz")
        tz = timezone(tz)
        return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Time for {username}: "
                                                    f"{datetime.now().astimezone(tz).strftime('%H:%M (%Z)')}")

    @command_manager.command("oct")
    async def offlinechattournament(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Offline Chat Tournament "
                                             "(osu! tournament for offline chat) https://oct.sheppsu.me")

    @command_manager.command("refresh_emotes", cooldown=Cooldown(60, 0))
    async def refresh_emotes(self, ctx):
        self.emotes[ctx.channel] = []  # sum(self.emote_requester.get_channel_emotes(ctx.channel), [])
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Emotes have been refreshed "
                                             f"(this command has a 1 minute cooldown).")


if __name__ == "__main__":
    bot = Bot(command_manager)
    bot.running = True
    bot.loop.run_until_complete(bot.start())
