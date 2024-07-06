# coding=utf-8
import asyncio

from dotenv import load_dotenv
load_dotenv(override=True)

try:
    from get_top_players import Client as TopPlayersClient
except:
    pass
from anime import create_list as create_anime_list
from sql import Database, USER_SETTINGS, Reminder
from emotes import EmoteRequester
from helper_objects import *
from context import *
from util import *
from constants import *
from lastfm import LastFMClient

import websockets
import os
import sys
# from client import Bot as CommunicationClient
from osu import (
    AsynchronousClient,
    Mods,
    Mod,
    GameModeInt,
    SoloScore,
    BeatmapsetSearchFilter,
    BeatmapsetSearchSort
)
from mal import Client as MALClient
import rosu_pp_py as rosu
from pytz import timezone, all_timezones
from aiohttp import client_exceptions, ClientSession as AiohttpClientSession
from datetime import datetime, timezone as tz, timedelta
from collections import defaultdict
from time import monotonic


TESTING = "--test" in sys.argv
LOCAL = "-local" in sys.argv

if not TESTING or not os.path.exists("data/top players (200).json"):
    TopPlayersClient().run()  # Update top player json file
if not TESTING or not os.path.exists("data/anime.json"):
    create_anime_list(MALClient.from_client_credentials(os.getenv("MAL_CLIENT_ID"), os.getenv("MAL_CLIENT_SECRET")))
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

    MWD_API_KEY = os.getenv("MWD_API_KEY")
    MWT_API_KEY = os.getenv("MWT_API_KEY")

    restarts = 0

    def __init__(self, cm, loop):
        self.database = Database()
        channels_to_run_in = [ChannelConfig("sheppsu", 156710598)] if TESTING else self.database.get_channels()

        self.cm = cm
        self.cm.init(self, channels_to_run_in)

        self.ws = None
        # self.comm_client = CommunicationClient(self)
        self.running = False
        self.loop = loop
        self.last_message = {}
        self.own_state = None
        self.irc_command_handlers = {
            ContextType.CONNECTED: self.on_running,
            ContextType.PRIVMSG: self.on_message,
            ContextType.USERSTATE: self.on_user_state,
            ContextType.JOIN: self.on_join,
        }

        # Is channel offline or not
        self.offlines = {channel.name: not channel.offlineonly for channel in self.cm.channels.values()}

        # Twitch api stuff
        self.twitch_client: TwitchAPIHelper = TwitchAPIHelper(os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET"))

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
        self.mw_cache = {"dictionary": {}, "thesaurus": {}, "args": {}}
        self.old_reminders = defaultdict(list)

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
            "emote": Scramble("emote", lambda channel: random.choice(self.emotes[channel]).name, 0.7,
                              ScrambleHintType.EVERY_OTHER, True, ScrambleRewardType.LOGARITHM),
            "anime": Scramble("anime", lambda: random.choice(self.anime[:250]), 1.1),
            "al": Scramble("azurlane ship", lambda: random.choice(self.azur_lane), 0.9),
        }
        self.scramble_manager = ScrambleManager(self.scrambles)

        # emote stuff
        self.emote_requester = EmoteRequester(self.twitch_client)
        self.emotes = {channel: [] for channel in self.cm.channels}

        # Bomb party
        self.bomb_party_helper = BombParty()
        self.bomb_party_future = None
        self.exploding = False

        # Anime compare
        self.compare_helper = AnimeCompare(self.anime)
        self.anime_compare_future = {}

        # osuguess
        self.osu_guess_helper = MapGuessHelper(self.loop)

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

        self.osu_client: AsynchronousClient | None = None

        try:
            self.MAX_MEDALS = int(requests.get("https://osekai.net/medals/api/public/count").text)
        except:
            print("Unable to fetch total medals from osekai")
            self.MAX_MEDALS = 0

        self.message_buffer = []

        # lastfm
        self.lastfm = LastFMClient()

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
        for reminder in self.database.get_reminders():
            self.old_reminders[reminder.channel].append(reminder)

    # Api request stuff
    # TODO: consider moving api stuff to its own class

    async def get_streams_status(self):
        # TODO: account for limit of 100
        channels = list(map(lambda c: c.id, filter(lambda c: c.offlineonly, self.cm.channels.values())))
        params = {"user_id": channels}

        data = await self.twitch_client.get("helix/streams", params=params)
        if data is None:
            for channel in self.cm.channels.values():
                self.offlines[channel.name] = not channel.offlineonly
            return

        data = data["data"]
        online_streams = [int(user["user_id"]) for user in data]
        user_logins = {channel.id: channel.name for channel in self.cm.channels.values()}
        
        for channel_id in channels:
            self.offlines[user_logins[channel_id]] = channel_id not in online_streams

    async def make_mw_req(self, endpoint, dictionary=True):
        cache = self.mw_cache["dictionary" if dictionary else "thesaurus"]
        if (value := cache.get(endpoint.lower(), None)) is not None:
            return value

        base, key = ("collegiate", self.MWD_API_KEY) if dictionary else ("thesaurus", self.MWT_API_KEY)
        async with AiohttpClientSession() as session:
            async with session.get(f"https://www.dictionaryapi.com/api/v3/references/{base}/json/{endpoint}?key={key}") as resp:
                if resp.status == 200:
                    cache[endpoint.lower()] = (data := await resp.json())
                    return data

                print(f"mw returned {resp.status}: {await resp.text()}")

    # Fundamental

    async def start(self):
        # start off by checking stream status of all channels
        # checking now will prevent some possible bugs
        await self.get_streams_status()

        self.osu_client = await AsynchronousClient.from_client_credentials(
            int(os.getenv("OSU_CLIENT_ID")), os.getenv("OSU_CLIENT_SECRET"), None
        )

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
                last_check = monotonic()
                last_ping = monotonic() - 60*60  # 1 hour
                last_cache_reset = monotonic()
                
                # comm_done = False
                while self.running:
                    await asyncio.sleep(1)  # Leave time for other stuff to run

                    # Check if channels are live
                    if monotonic() - last_check >= 10:
                        await self.get_streams_status()
                        last_check = monotonic()

                    # Ping database once an hour for keepalive
                    if monotonic() - last_ping >= 60*60:
                        last_ping = monotonic()
                        self.database.ping()

                    if monotonic() - last_cache_reset >= 60*60:
                        # to prevent the cache from growing too large
                        self.mw_cache["dictionary"] = {}
                        self.mw_cache["thesaurus"] = {}

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
        print(f"Connecting to irc server as {self.username}")
        await self.ws.send(f"PASS {self.oauth}")
        await self.ws.send(f"NICK {self.username}")

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
        # probably reconnecting to the channel
        if ctx.channel in self.message_locks:
            return
        try:
            channel_id = self.cm.channels[ctx.channel].id
        except KeyError:
            channel_id = None

        self.message_locks[ctx.channel] = asyncio.Lock()
        self.last_message[ctx.channel] = ""
        self.recent_score_cache[ctx.channel] = {}
        self.trivia_helpers[ctx.channel] = TriviaHelper()
        self.mw_cache["args"][ctx.channel] = {"word": "",  "index": 1}
        for reminder in self.old_reminders.pop(ctx.channel, []):
            self.set_reminder_event(reminder)

        try:
            self.emotes[ctx.channel] = await self.emote_requester.get_channel_emotes(channel_id or ctx.channel)
        except KeyError:
            self.emotes[ctx.channel] = []

    async def on_message(self, ctx: MessageContext):
        # check if should respond
        if (ctx.channel in self.offlines and not self.offlines[ctx.channel]) or \
                ctx.user.username == self.username:
            return

        # for pogpega man
        if ctx.message.lower().startswith("pogpega") and ctx.message.lower() != "pogpega":
            ctx.message = ctx.message[8:]

        ascii_message = "".join([char for char in ctx.message if char.isascii()]).strip()

        # check scrambles
        for scramble_type, scramble in self.scrambles.items():
            if scramble.in_progress(ctx.channel):
                await self.on_scramble(ctx, scramble_type)

        # check anime compares
        if ctx.user.username in self.anime_compare_future and self.anime_compare_future[ctx.user.username] is not None and \
                ascii_message.isdigit() and int(ascii_message.strip()) in range(1, 3):
            game = self.compare_helper.get_game(ctx.user.username)
            if game is not None:
                await self.on_anime_compare(ctx, game)

        # check trivias
        elif self.trivia_helpers[ctx.channel].is_in_progress and ascii_message.isdigit() and \
                int(ascii_message.strip()) in range(1, 5):
            message = int(ascii_message)
            await self.on_answer(ctx, message)

        # check bomb party
        if self.bomb_party_helper.started:
            await self.on_bomb_party(ctx)

        # check afks
        await self.on_afk(ctx)

        # check osu_guess
        if (money := self.osu_guess_helper.check(ctx.channel, ctx.message)) != 0:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Correct! You get {money} Becky Bucks."
            )
            self.database.add_money(ctx, money)
            return

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
            value = {"on": 1, "off": 0}[args[1].lower()]
        except KeyError:
            return await self.send_message(ctx.channel, "You must specify on or off.")

        self.database.update_userdata(ctx, setting, str(value))
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
        if (datetime.now(tz=tz.utc) - afk.time.replace(tzinfo=tz.utc)).total_seconds() > 60:
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
        osu_user = self.database.get_osu_user_from_user_id(ctx.user_id)
        if osu_user is not None:
            self.osu_user_id_cache[osu_user[1]] = osu_user[0]
            return osu_user[0]
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Please specify a username or link your account with !link [username]."
        )

    async def process_osu_mode_args(self, ctx, args, required=True, as_int=False):
        arg = self.process_value_arg("-m", args, 0)
        if arg is None and required:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must specify a mode with the -m argument. "
                "Valid modes are 0 (osu), 1 (taiko), 2 (catch), 3 (mania)."
            )
            return
        elif not required:
            return -1
        if isinstance(arg, str) and (not arg.isdigit() or int(arg) not in range(0, 4)):
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Invalid mode. Valid modes "
                "are 0 (osu), 1 (taiko), 2 (catch), 3 (mania)."
            )
            return
        return int(arg) if as_int else ("osu", "taiko", "fruits", "mania")[int(arg)]

    async def process_index_arg(self, ctx, args, rng=range(1, 101)):
        arg = self.process_value_arg("-i", args, -1)
        if arg == -1:
            return -1
        if arg is None:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must specify an index with the -i argument. "
                f"Specify a number between {rng[0]} and {rng[-1]}"
            )
            return
        if arg.lower() == "random":
            return random.choice(rng)-1
        if type(arg) != int and (not arg.isdigit() or int(arg) not in rng):
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must specify a number between "
                f"{rng[0]} and {rng[-1]} for the -i argument."
            )
            return
        return int(arg)-1

    async def get_osu_user_id_from_osu_username(self, ctx, username):
        if username not in self.osu_user_id_cache:
            user = await self.osu_client.get_user(user=username, key="username")
            if user is None:
                await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")
                return
            self.osu_user_id_cache[username] = user.id
        return self.osu_user_id_cache[username]

    @staticmethod
    def get_mod_string(mods):
        def fmt_settings(m):
            if m.settings is None:
                return ""

            if "speed_change" in m.settings:
                return f"({round(m.settings['speed_change'], 2)}x)"

            if Mod.DifficultyAdjust == m.mod:
                return f"({'|'.join((''.join(map(lambda s: s[0], k.upper().split('_')))+f'={v}' for k, v in m.settings.items()))})"

            return ""

        return "".join(map(
            lambda m: m.mod.value+fmt_settings(m),
            mods
        ))
    
    def get_score_attrs(self, calc, score):
        perf = calc.calculate(score)
        fc_perf, fc_acc = calc.calculate_if_fc(score) if (
            (perf.effective_miss_count is not None and perf.effective_miss_count >= 1) or 
            not score.passed or
            (score.statistics.miss is not None and score.statistics.miss > 0)
        ) else (None, None)
        hits = BeatmapCalculator.parse_stats(score.statistics)
        return perf, fc_perf, fc_acc, hits

    async def get_score_message(self, score: SoloScore, prefix="Recent score for {username}") -> tuple[str, BeatmapCalculator]:
        score_format = prefix+":{passed} {artist} - {title} [{diff}]{mods} ({mapper}, {star_rating}*) " \
                    "{acc}% {combo}/{max_combo} | ({genki_counts}) | {pp}{if_fc_pp} | {time_ago} ago"

        calc = await BeatmapCalculator.from_beatmap_id(score.beatmap_id)
        perf, fc_perf, fc_acc, hits = self.get_score_attrs(calc, score)

        bm_perf = fc_perf if not score.passed else perf

        return score_format.format(**{
            "username": score.user.username,
            "passed": "" if score.passed else f" (Failed {round(sum(hits) / calc.beatmap.n_objects * 100)}%)",
            "artist": calc.info.metadata.artist,
            "title": calc.info.metadata.title,
            "diff": calc.info.metadata.version,
            "mods": " +" + self.get_mod_string(score.mods) if score.mods else "",
            "mapper": calc.info.metadata.creator,
            "star_rating": round(bm_perf.difficulty.stars, 2),
            "pp": f"{round(perf.pp, 2)}pp",
            "if_fc_pp": f" ({round(fc_perf.pp, 2)} for {round(fc_acc * 100, 2)}% FC)" if fc_perf is not None else "",
            "acc": round(score.accuracy * 100, 2),
            "combo": score.max_combo,
            "max_combo": bm_perf.difficulty.max_combo,
            "genki_counts": BeatmapCalculator.hits_to_string(hits, score.ruleset_id),
            "time_ago": format_date(score.ended_at)
        }), calc

    async def get_compact_scores_message(self, scores) -> str:
        score_format = "{artist} - {title} [{diff}]{mods} ({sr}*) {acc}% ({genki_counts}): {pp}pp{fc_pp} | {time_ago} ago"
        message = ""
        calcs: tuple[BeatmapCalculator] = await asyncio.gather(
            *(BeatmapCalculator.from_beatmap_id(score.beatmap_id) for score in scores)
        )
        for calc, score in zip(calcs, scores):
            perf, fc_perf, fc_acc, hits = self.get_score_attrs(calc, score)

            message += "🌟" + score_format.format(**{
                "artist": calc.info.metadata.artist,
                "title": calc.info.metadata.title,
                "diff": calc.info.metadata.version,
                "mods": " +" + self.get_mod_string(score.mods) if score.mods else "",
                "sr": round((perf if score.passed else fc_perf).difficulty.stars, 2),
                "acc": round(score.accuracy * 100, 2),
                "genki_counts": BeatmapCalculator.hits_to_string(hits, score.ruleset_id),
                "pp": round(perf.pp, 2),
                "fc_pp": f" ({round(fc_perf.pp, 2)} for {round(fc_acc * 100, 2)}% FC)" if fc_perf is not None else "",
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

    def get_map_cache(self, ctx) -> BeatmapCalculator | None:
        if len(self.recent_score_cache[ctx.channel]) == 0:
            return
        if ctx.reply:
            if ctx.reply.msg_body in self.recent_score_cache[ctx.channel]:
                return self.recent_score_cache[ctx.channel][ctx.reply.msg_body]
            return
        return tuple(self.recent_score_cache[ctx.channel].values())[-1]

    def add_recent_map(self, ctx, sent_message, bm_calc):
        msg = " ".join(sent_message)
        if msg in self.recent_score_cache[ctx.channel]:
            del self.recent_score_cache[ctx.channel][msg]
        self.recent_score_cache[ctx.channel].update({msg: bm_calc})
        while len(self.recent_score_cache) > 50:
            del self.recent_score_cache[ctx.channel][next(self.recent_score_cache[ctx.channel].keys())]

    async def get_beatmap_from_arg(self, ctx, beatmap_link):
        beatmap_id = tuple(filter(lambda s: len(s.strip()) > 0, beatmap_link.split("/")))[-1]
        calc = await BeatmapCalculator.from_beatmap_id(beatmap_id)
        if calc is None:
            return await self.send_message(ctx.channel, "Failed to get beatmap from the provided link/id.")
        return calc

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
            scores = await self.osu_client.get_user_scores(
                user_id, "recent", include_fails=1, mode=mode, limit=1, offset=index
            )
        else:
            scores = await self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=100)
            scores = sorted(scores, key=lambda x: x.ended_at, reverse=True)
        if not scores:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} "
                                                        f"has no recent scores for {proper_mode_name[mode]} "
                                                        "or the index you specified is out of range.")

        score = scores[0 if not best else index]
        msg, calc = await self.get_score_message(score)
        sent_message = await self.send_message(ctx.channel, msg)
        self.add_recent_map(ctx, sent_message, calc)

    @command_manager.command("c", aliases=['compare'], cooldown=Cooldown(0, 3))
    async def compare_score(self, ctx):
        if not len(self.recent_score_cache[ctx.channel]):
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} I don't have a cache of the last beatmap."
            )
        cache = self.get_map_cache(ctx)
        if cache is None:
            return
        await self.compare_score_func(ctx, cache)

    async def compare_score_func(self, ctx, cache=None):
        calc = self.get_map_cache(ctx) if cache is None else cache
        if calc is None:
            return

        args = ctx.get_args('ascii')
        mode = await self.process_osu_mode_args(ctx, args, required=False, as_int=True)
        if mode is None:
            return
        elif mode == -1:
            mode = int(calc.beatmap.mode)

        user_id = await self.get_osu_user_id_from_args(ctx, args)
        if user_id is None:
            return
        username = self.osu_username_from_id(user_id)

        if mode != int(calc.beatmap.mode):
            calc.beatmap.convert(rosu.GameMode(mode))

        mode = GameModeInt.get_str_equivalent(GameModeInt(mode)).value

        try:
            scores = await self.osu_client.get_user_beatmap_scores(calc.beatmap_id, user_id, mode)
        except client_exceptions.ClientResponseError:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Either this map does not have a leaderboard or "
                "an unexpected error occurred"
            )
        if not scores:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} User {username} has no "
                f"scores on that beatmap for mode {proper_mode_name[mode]}."
            )

        score_format = "{mods} {acc}% {combo}/{max_combo} | ({genki_counts}) | {pp} | {time_ago} ago"
        message = f"Scores for {username} on {calc.info.metadata.artist} - {calc.info.metadata.title} " \
                  f"[{calc.info.metadata.version}] ({calc.info.metadata.creator}): "
        for score in scores[:5]:
            perf = calc.calculate(score)
            hits = calc.parse_stats(score.statistics)
            message += "🌟" + score_format.format(**{
                "mods": " +" + "".join(map(lambda m: m.mod.value, score.mods)) if score.mods else "",
                "acc": round(score.accuracy * 100, 2),
                "combo": score.max_combo,
                "max_combo": perf.difficulty.max_combo,
                "genki_counts": BeatmapCalculator.hits_to_string(hits, score.ruleset_id),
                "pp": f"{round(perf.pp, 2)}pp",
                "time_ago": format_date(score.ended_at)
            })
        sent_message = await self.send_message(ctx.channel, message)
        self.add_recent_map(ctx, sent_message, calc)

    async def get_beatmap_from_arg_or_cache(self, ctx, args):
        if len(args) > 0:
            return await self.get_beatmap_from_arg(ctx, args[0])
        elif len(self.recent_score_cache[ctx.channel]) == 0:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} I don't have a cache of the last beatmap."
            )
        else:
            return self.get_map_cache(ctx)

    @command_manager.command("map", aliases=["m"])
    async def send_map(self, ctx):
        args = ctx.get_args('ascii')

        calc = await self.get_beatmap_from_arg_or_cache(ctx, args)
        if calc is None:
            return

        diff = rosu.Difficulty().calculate(calc.beatmap)
        text = (
            f"{calc.info.metadata.artist} - {calc.info.metadata.title} [{calc.info.metadata.version}] "
            f"({calc.info.metadata.creator}, {round(diff.stars, 2)}*) "
            f"https://osu.ppy.sh/b/{calc.beatmap_id}"
        )
        sent_message = await self.send_message(ctx.channel, f"@{ctx.user.display_name} {text}")
        self.add_recent_map(ctx, sent_message, calc)

    @command_manager.command("osu", aliases=["profile", "o"], cooldown=Cooldown(0, 5))
    async def osu_profile(self, ctx):
        args = ctx.get_args('ascii')
        mode = await self.process_osu_mode_args(ctx, args)
        if mode is None:
            return
        user = await self.get_osu_user_id_from_args(ctx, args)
        if user is None:
            return
        username = self.osu_username_from_id(user)

        try:
            user = await self.osu_client.get_user(user=user, mode=mode, key="username" if type(user) == str else "id")
        except client_exceptions.ClientResponseError:
            return await self.send_message(ctx.channel, f"{ctx.user.display_name} A user with the name {username} "
                                                        "does not exist. If they did before it's possible they "
                                                        "got restricted or had their account deleted.")

        if user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")

        stats = user.statistics
        if (rank_history := user.rank_history) is not None:
            rank_history = user.rank_history.data
            rank_direction = rank_history[min(len(rank_history), 29)] - rank_history[-1]
            rank_direction = ("↑" if rank_direction >= 0 else "↓") + str(abs(rank_direction))

        profile_layout = (
            "{username}'s profile [{mode}]: #{global_rank}{rank_direction} ({country}#{country_rank}) - "
            "{pp}pp; Peak: #{peak_rank} {peak_time_ago} ago | {accuracy}% | {play_count} playcount "
            "({play_time} hrs) | Medal count: {medal_count}/{total_medals} ({medal_completion}%) | "
            "Followers: {follower_count} | Mapping subs: {subscriber_count}"
        )
        await self.send_message(ctx.channel, profile_layout.format(**{
            "username": user.username,
            "mode": proper_mode_name[mode],
            "rank_direction": " "+rank_direction if rank_history is not None else "",
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
            "total_medals": self.MAX_MEDALS,
            "medal_completion": round(len(user.user_achievements) / self.MAX_MEDALS * 100, 2),
            "follower_count": user.follower_count,
            "subscriber_count": user.mapping_follower_count,
        }))

    @command_manager.command("osutop", cooldown=Cooldown(0, 5))
    async def osu_top(self, ctx):
        args = ctx.get_args('ascii')

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

        top_scores = await self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=100)
        if not top_scores:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} User {username} has no top scores for {proper_mode_name[mode]}."
            )
        if recent_tops:
            top_scores = sorted(top_scores, key=lambda x: x.ended_at, reverse=True)
        top_scores = top_scores[:5] if index == -1 else [top_scores[index]]
        username = top_scores[0].user.username

        calc = None
        if len(top_scores) > 1:
            message = f"Top{' recent' if recent_tops else ''} {proper_mode_name[mode]} " \
                      f"scores for {username}: " if index == -1 else f"Top {index+1}{' recent' if recent_tops else ''} " \
                                                                     f"{proper_mode_name[mode]} score for {username}: "
            message += await self.get_compact_scores_message(top_scores)
        else:
            score = top_scores[0]
            message, calc = await self.get_score_message(
                score, f"Top {index+1}{' recent' if recent_tops else ''} score for {username}"
            )

        sent_message = await self.send_message(ctx.channel, message)
        if calc is not None:
            self.add_recent_map(ctx, sent_message, calc)

    @command_manager.command("link", cooldown=Cooldown(0, 2))
    async def link_osu_account(self, ctx):
        args = ctx.get_args('ascii')
        if len(args) == 0 or args[0].strip() == "":
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Please specify a username.")

        username = " ".join(args).strip()
        user = await self.osu_client.get_user(user=username, key="username")

        if user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")

        osu_user = self.database.get_osu_user_from_user_id(ctx.user_id)
        if osu_user is not None:
            self.database.update_osu_data(ctx.user_id, user.username, user.id)
        else:
            self.database.new_osu_data(ctx.user_id, user.username, user.id)
        self.osu_user_id_cache[user.username] = user.id

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Linked {user.username} to your account.")

    @command_manager.command("simulate", cooldown=Cooldown(0, 2), aliases=["s"])
    async def simulate_score(self, ctx):
        if len(self.recent_score_cache[ctx.channel]) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} I don't have a cache of the last beatmap.")
        calc = self.get_map_cache(ctx)
        if calc is None:
            return

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

        calc.calculate_difficulty(0 if mods is None else mods.value)

        pp_values = []
        for acc in (1, 0.99, 0.98, 0.97, 0.96, 0.95):
            perf = calc.calculate_from_acc(acc)
            pp_values.append(f"{int(acc*100)}% - {round(perf.pp, 2)}")

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} {calc.info.metadata.artist} - "
            f"{calc.info.metadata.title} [{calc.info.metadata.version}] "
            f"{mods.to_readable_string() if mods is not None else 'NM'}: "
            f"{' | '.join(pp_values)}"
        )

    @command_manager.command("score", aliases=["sc"])
    async def osu_score(self, ctx):
        args = ctx.get_args('ascii')

        if len(args) < 1:
            return await self.send_message(ctx.channel, "Must give a beatmap link or beatmap id.")
        calc = await self.get_beatmap_from_arg(ctx, args[0])
        if calc is None:
            return

        i = ctx.message.index(args[0])
        ctx.message = (ctx.message[:i] + ctx.message[i+len(args[0])+1:]).strip()

        await self.compare_score_func(ctx, calc)
        
    @command_manager.command("send_map", aliases=["sm"])
    async def send_osu_map(self, ctx):
        return await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Sorry! This command is temporarily disabled."
        )

        calc = self.get_map_cache(ctx)
        if calc is None:
            return
        osu_user = self.database.get_osu_user_from_user_id(ctx.user_id)
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

        md = calc.info.metadata
        bms_title = f"{md.artist} - {md.title} [{md.version}] mapped by {md.creator}"
        await self.osu_client.create_new_pm(osu_user[0], f"(Automated bot message) [{bms_title}](https://osu.ppy.sh/b/{md.beatmap_id})", False)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Sent the beatmap to your osu DMs!")

    @command_manager.command("preview", aliases=["p"])
    async def send_osu_preview(self, ctx):
        args = ctx.get_args("ascii")
        calc = await self.get_beatmap_from_arg_or_cache(ctx, args)
        if calc is None:
            return

        md = calc.info.metadata
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} {md.artist} - {md.title} [{md.version}] "
            f"https://preview.tryz.id.vn/?b={calc.beatmap_id}"
        )

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

    async def send_reminder_msg(self, reminder: Reminder):
        user = self.database.get_user_from_user_id(reminder.user_id)
        # this *shouldn't* occur
        if user is None:
            return

        await self.send_message(reminder.channel, f"@{user.username} DinkDonk Reminder! {reminder.message}")
        self.database.finish_reminder(reminder.id)

    def set_reminder_event(self, reminder: Reminder):
        length = max(0.0, (reminder.end_time - datetime.now(tz=tz.utc)).total_seconds())
        self.set_timed_event(length, self.send_reminder_msg, reminder)

    async def time_text_to_timedelta(self, ctx, text: str) -> timedelta | None:
        time_multipliers = {
            "s": 1,
            "m": 60,
            "h": 60 * 60,
            "d": 60 * 60 * 24,
            "w": 60 * 60 * 24 * 7
        }

        if (cc := text.count(":")) > 0:
            if cc > 1:
                return await self.send_message(ctx.channel, "Must specify times in XX:XX format Nerdge")

            tz = self.database.get_user_timezone(ctx.user_id)
            if tz is None:
                return await self.send_message(
                    ctx.channel,
                    "You need to link a timezone with !linktz to use time reminders"
                )

            try:
                hour, minute = tuple(map(int, text.split(":")))
            except ValueError:
                return await self.send_message(ctx.channel, "Not a valid integer Nerdge")

            tz = timezone(tz)
            now = datetime.now(tz=tz)
            future = now.replace(hour=hour, minute=minute)
            if now >= future:
                future += timedelta(hours=24)
            return future - now

        suffix = text[-1].lower()
        if suffix not in time_multipliers:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} the time must end with s, m, h, d, or w Nerdge"
            )

        try:
            return timedelta(seconds=round(float(text[:-1])*time_multipliers[suffix]))
        except ValueError:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} not a valid number Nerdge")

    @command_manager.command("remind", aliases=["reminder", "remindme"])
    async def set_reminder(self, ctx):
        args = ctx.get_args()
        if len(args) == 0:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must give a time (10s, 20m, 1.5h, 3.2d, ...) Chatting"
            )

        now = datetime.now(tz=tz.utc)
        length = await self.time_text_to_timedelta(ctx, args[0])
        if not isinstance(length, timedelta):
            return
        if length.total_seconds() < 60:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Reminder must be at least a minute Nerdge"
            )
        
        reminder = self.database.create_reminder(ctx, now+length, " ".join(args[1:]))
        self.set_reminder_event(reminder)

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Set reminder to occur in {format_date(now-length)} YIPPEE"
        )
        
    @command_manager.command("osulb")
    async def offline_chat_osu_leaderboard(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} https://bot.sheppsu.me/osu/")

    @staticmethod
    def parse_mw_text(text):
        def parse_mark(mark):
            for m in ("a_link", "d_link", "i_link", "et_link", "mat", "sx", "dxt"):
                if mark.startswith(m):
                    return mark.split("|")[1]
            return {
                "bc": ":"
            }.get(mark, "")

        while "{" in text:
            start = text.index("{")
            end = text.index("}")
            text = text[:start] + parse_mark(text[start+1:end]) + text[end+1:]
        return text

    async def parse_mw_args(self, ctx, dictionary=True):
        args = ctx.get_args()
        last_args = self.mw_cache["args"][ctx.channel] or {}

        index = self.process_value_arg("-i", args, last_args["index"])
        if type(index) == str and not index.isdigit():
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Index must be an integer")

        if len(args) == 0 and len(last_args["word"]) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Specify a word to lookup")
        elif len(args) != 0 and type(index) == int:
            # default to index 1 when word is specified but not index
            index = 1

        word = " ".join(args) or last_args["word"]
        index = int(index)
        data = await self.make_mw_req(word, dictionary=dictionary)

        if data is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Something went wrong when communicating with the Merriam-Webster api"
            )

        if len(data) == 0:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} that word does not exist in the Merriam-Webster collegiate dictionary"
            )

        if type(data[0]) == str:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Could not find that word. Did you mean one of these words: {', '.join(data)}"
            )

        if index not in range(1, len(data)+1):
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Index must be between 1 and {len(data)}"
            )

        self.mw_cache["args"][ctx.channel]["word"] = word
        self.mw_cache["args"][ctx.channel]["index"] = index

        return data[index-1], index, len(data)

    @staticmethod
    def parse_definition(data) -> str | None:
        if (definition := data.get("def", None)) is None:
            return

        definition = MWDefinition(definition[0])

        def get_text(definition):
            return next(filter(lambda item: isinstance(item, MWSenseDefinitionText), definition.items)).content

        seq = definition.sense_sequences[0]
        sense = seq.senses[0]
        if isinstance(sense, MWBindingSense):
            sense = sense.sense
        if isinstance(sense, MWSense):
            return get_text(sense.definition)

        text = ""
        for i, sense in enumerate(sense):
            if isinstance(sense, MWBindingSense):
                sense = sense.sense
            if i != 0 and sense.sense_number is not None:
                text += f"{sense.sense_number} "
            text += get_text(sense.definition)

        return text

    @staticmethod
    def parse_example(data):
        if (definition := data.get("def", None)) is None:
            return

        definition = MWDefinition(definition[0])

        def find_example(sense):
            if isinstance(sense, MWBindingSense):
                sense = sense.sense

            if sense.definition is not None:
                for item in sense.definition.items:
                    if isinstance(item, MWSenseVerbalIllustration):
                        return item.items[0]["t"]

            if sense.divided_sense is not None:
                return find_example(sense.divided_sense)

        # I love MW response format!!!!!
        for seq in definition.sense_sequences:
            for sense in seq.senses:
                if isinstance(sense, MWSense):
                    sense = [sense]
                for sense in sense:
                    example = find_example(sense)
                    if example is not None:
                        return example

    @command_manager.command("define", aliases=["def"])
    async def define_word(self, ctx):
        ret = await self.parse_mw_args(ctx)
        if type(ret) != tuple:
            return
        data, index, length = ret

        word = data["meta"]["id"].split(":")[0]
        definition = self.parse_definition(data)
        if definition is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} ({index}/{length}) {word} :No definition available for this index"
            )

        fl = data["fl"]
        date = data.get("date")
        date = f" | from {self.parse_mw_text(date)}" if date is not None else ""

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ({index}/{length}) {word} [{fl}] {self.parse_mw_text(definition)}{date}"
        )

    @command_manager.command("example")
    async def example_word(self, ctx):
        ret = await self.parse_mw_args(ctx)
        if type(ret) != tuple:
            return
        data, index, length = ret

        word = data["meta"]["id"].split(":")[0]
        example = self.parse_example(data)
        if example is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} ({index}/{length}) {word} :No example available for this index"
            )

        fl = data["fl"]
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ({index}/{length}) {word} [{fl}] {self.parse_mw_text(example)}"
        )

    @command_manager.command("synonyms")
    async def synonyms_word(self, ctx):
        ret = await self.parse_mw_args(ctx, dictionary=False)
        if type(ret) != tuple:
            return
        data, index, length = ret

        word = data["meta"]["id"].split(":")[0]
        fl = data["fl"]
        syns = sum(data["meta"]["syns"], [])[:20]
        if len(syns) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} this word has no synonym entries")
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ({index}/{length}) {word} [{fl}]: {', '.join(syns)}"
        )

    @command_manager.command("antonyms")
    async def antonyms_word(self, ctx):
        ret = await self.parse_mw_args(ctx, dictionary=False)
        if type(ret) != tuple:
            return
        data, index, length = ret

        if type(data) == str:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} this word has no antonym entries")

        word = data["meta"]["id"].split(":")[0]
        fl = data["fl"]
        ants = sum(data["meta"]["ants"], [])[:20]
        if len(ants) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} this word has no antonym entries")

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ({index}/{length}) {word} [{fl}]: {', '.join(ants)}"
        )

    @command_manager.command("lastfm_link", aliases=["fmlink"])
    async def link_lastfm(self, ctx):
        args = ctx.get_args('ascii')
        if len(args) == 0 or args[0].strip() == "":
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Please specify a username.")

        username = " ".join(args).strip()
        user = self.lastfm.get_lastfm_user(username)

        if user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")

        username = user['user']['name']

        # check whether they've linked before
        if self.database.get_lastfm_user_from_user_id(ctx.user_id) is not None:
            self.database.update_lastfm_data(ctx.user_id, username)
        else:
            self.database.new_lastfm_data(ctx.user_id, username)

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Linked {username} to your account.")
    
    @command_manager.command("lastfm_np", aliases=["fmnp"])
    async def lastfm_np(self, ctx):
        lastfm_user = self.database.get_lastfm_user_from_user_id(ctx.user_id)
        if lastfm_user is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You don't have a username linked to LastFM, "
                f"you can do !fmlink *username* to link your account."
            )
        
        recent_song = self.lastfm.get_recent_song(lastfm_user[0])

        if "@attr" in recent_song['recenttracks']['track'][0]:
            song_title = recent_song['recenttracks']['track'][0]['name']
            song_artist = recent_song['recenttracks']['track'][0]['artist']['name']
            song_url = recent_song['recenttracks']['track'][0]['url']
            return await self.send_message(
                ctx.channel,
                f"Now playing for {lastfm_user[0]}: {song_artist} - {song_title} | {song_url}"
            )

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You are not currently playing anything.")

    @command_manager.command("update_userdata", aliases=["updateud"])
    async def update_userdata(self, ctx):
        self.database.update_userdata(ctx, "username", ctx.sending_user)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} updated your username for userdata")

    @command_manager.command("osuguess")
    async def osu_guess(self, ctx):
        if self.osu_guess_helper.in_progress(ctx.channel):
            return

        args = ctx.get_args("ascii")

        difficulty = self.process_value_arg("-d", args, "easy")
        try:
            i = random.randint(*{
                "easy": (0, 499),
                "medium": (500, 999),
                "hard": (1000, 1999)
            }[difficulty.lower()])
        except KeyError:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Invalid difficulty. Valid difficulties are easy, medium, hard"
            )

        valid_attrs = ["artist", "title", "difficulty", "mapper"]
        if len(args) > 0:
            try:
                attr_i = valid_attrs.index(args[0].lower())
            except ValueError:
                return await self.send_message(
                    ctx.channel,
                    f"@{ctx.user.display_name} valid guess types are artist, title, difficulty, or mapper. "
                    "Specify nothing for random."
                )
        else:
            attr_i = None

        beatmapset = (await self.osu_client.search_beatmapsets(
            BeatmapsetSearchFilter().set_sort(BeatmapsetSearchSort.PLAYS).set_mode(GameModeInt.STANDARD),
            i//50+1
        )).beatmapsets[i % 50]
        await self.send_message(
            ctx.channel,
            self.osu_guess_helper.new(
                ctx.channel,
                beatmapset,
                lambda answer: self.send_message(
                    ctx.channel,
                    f"Time ran out for osuguess. The answer was {answer}."
                ),
                40 + (i // 40),
                attr_i
            )
        )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    bot = Bot(command_manager, loop)
    bot.running = True
    loop.run_until_complete(bot.start())
