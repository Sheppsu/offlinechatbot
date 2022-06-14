# coding=utf-8

# TODO: channel specific commands
#       clean up code in general
#       utilize DMs
#       different rate limits for mods and broadcaster
#       stop trying to restart after a certain amount of failed attempts in a row

from dotenv import load_dotenv
load_dotenv()

import websockets
import requests
import html
import os
from get_top_players import Client
from sql import Database
from emotes import EmoteRequester
from helper_objects import *
from util import *
from constants import *


Client().run()  # Update top player json file

TESTING = True if len(sys.argv) > 1 and sys.argv[1] == "--test" else False


class Bot:
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    username = "sheepposubot"
    oauth = os.getenv("OAUTH")
    uri = "ws://irc-ws.chat.twitch.tv:80"
    channel_to_run_in = "btmc" if not TESTING else "sheepposu"

    # Save/load data from files or to/from database
    pity: dict
    gamba_data: dict
    top_players: list
    top_maps: list
    word_list: list
    facts: list
    pull_options: dict
    afk: dict
    all_words: list

    restarts = 0

    def __init__(self):
        self.ws = None
        self.running = False
        self.loop = asyncio.get_event_loop()
        self.future_objects = []

        # Is ed offline or not
        self.offline = True

        # Twitch api stuff
        self.access_token, self.expire_time = self.get_access_token()
        self.expire_time += perf_counter()

        # Message related variables
        self.message_send_cd = 1.5
        self.last_message = 0
        self.message_lock = asyncio.Lock()

        # Command related variables
        self.commands = {
            "pull": self.pull,
            "genshinpull": self.pull,
            "guess": self.guess,
            "font": self.font,
            "fonts": self.fonts,
            # "trivia": self.trivia,
            'slap': self.slap,
            "pity": self.pity,
            "scramble": lambda ctx: self.scramble(ctx, "word"),
            "hint": lambda ctx: self.hint(ctx, "word"),
            "scramble_osu": lambda ctx: self.scramble(ctx, "osu"),
            "hint_osu": lambda ctx: self.hint(ctx, "osu"),
            "scramble_map": lambda ctx: self.scramble(ctx, "map"),
            "hint_map": lambda ctx: self.hint(ctx, "map"),
            "scramble_genshin": lambda ctx: self.scramble(ctx, "genshin"),
            "hint_genshin": lambda ctx: self.hint(ctx, "genshin"),
            "scramble_emote": lambda ctx: self.scramble(ctx, "emote"),
            "hint_emote": lambda ctx: self.hint(ctx, "emote"),
            "bal": self.balance,
            "leaderboard": self.leaderboard,
            "sheepp_filter": self.filter,
            "give": self.give,
            "toggle": self.toggle,
            "balance_market": self.market_balance,
            "ranking": self.get_ranking,
            "rps": self.rps,
            "new_name": self.new_name,
            "scramble_multiplier": self.scramble_difficulties,
            "scramble_calc": self.scramble_calc,
            "afk": self.afk,
            "help": self.help_command,
            "sheeppcommands": self.help_command,
            "sheepp_help": self.help_command,
            "sheepp_commands": self.help_command,
            "trivia_category": self.trivia_category,
            "sourcecode": self.sourcecode,
            "bombparty": self.bomb_party,
            "start": self.start_bomb_party,
            "join": self.join_bomb_party,
            "leave": self.leave_bomb_party,
            "settings": self.change_bomb_settings,
            "players": self.player_list,
            "funfact": self.random_fact,
            "reload_db": self.reload_from_db,
            "reload_emotes": self.refresh_emotes,
        }  # Update pastebins when adding new commands
        self.cooldown = {}
        self.overall_cooldown = {}

        # Guess the number
        self.number = random.randint(1, 1000)

        # Trivia
        # TODO: move to a class
        self.answer = None
        self.guessed_answers = []
        self.trivia_future = None
        self.trivia_diff = None
        self.trivia_info = {
            "hard": 100,
            "medium": 40,
            "easy": 20,
            "penalty": 0.25,
            "decrease": 0.5,
        }

        self.scrambles = {
            "word": Scramble("word", lambda: random.choice(self.word_list), 1),
            "osu": Scramble("player name", lambda: random.choice(self.top_players), 0.8),
            "map": Scramble("map name", lambda: random.choice(self.top_maps), 1.3),
            "genshin": Scramble("genshin weap/char", lambda: random.choice(self.genshin), 0.7),
            "emote": Scramble("emotes", lambda channel: random.choice(self.emotes[channel]).name, 0.6, ScrambleHintType.EVERY_OTHER, True),
        }
        self.scramble_manager = ScrambleManager(self.scrambles)

        # Load emotes
        self.emotes = self.load_emotes()

        # Bomb party
        self.bomb_party_helper = BombParty()
        self.bomb_party_future = None

        # Data
        self.database = Database()

        # Load save data
        self.load_data()

    # Util

    def is_on_cooldown(self, command, user, user_cd=10, cmd_cd=5):
        if command not in self.overall_cooldown:
            self.overall_cooldown.update({command: perf_counter()})
            return False
        if perf_counter() - self.overall_cooldown[command] < cmd_cd:
            return True
        if command not in self.cooldown:
            self.cooldown.update({command: {user: perf_counter()}})
            return False
        if user not in self.cooldown[command]:
            self.cooldown[command].update({user: perf_counter()})
            self.overall_cooldown[command] = perf_counter()
            return False
        if perf_counter() - self.cooldown[command][user] < user_cd:
            return True
        self.cooldown[command][user] = perf_counter()
        self.overall_cooldown[command] = perf_counter()
        return False

    def set_timed_event(self, wait, callback, *args, **kwargs):
        return asyncio.run_coroutine_threadsafe(do_timed_event(wait, callback, *args, **kwargs), self.loop)

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

    def load_facts(self):
        with open("data/facts.json", "r") as f:
            self.facts = json.load(f)

    def load_all_words(self):
        with open("data/all_words.json", "r") as f:
            self.all_words = [word.lower() for word in json.load(f)]

    def load_db_data(self):
        self.pity = self.database.get_pity()
        self.gamba_data = self.database.get_userdata()
        self.afk = self.database.get_afk()

    def load_emotes(self):
        emote_requester = EmoteRequester(self.client_id, self.client_secret)
        return {
            self.channel_to_run_in: sum(emote_requester.get_channel_emotes(self.channel_to_run_in), []),
            self.username: sum(emote_requester.get_channel_emotes(self.username), [])
        }

    def load_genshin(self):
        with open("data/genshin.json", "r") as f:
            self.pull_options = json.load(f)

    def load_data(self):
        self.load_top_players()
        self.load_top_maps()
        self.load_words()
        self.load_facts()
        self.load_all_words()
        self.load_genshin()
        self.load_db_data()

    def save_money(self, user):
        self.database.update_userdata(user, 'money', round(self.gamba_data[user]['money']))

    # Api request stuff
    # TODO: consider moving api stuff to its own class

    def load_top_plays(self):  # To be used in the future maybe
        resp = requests.get('https://osutrack-api.ameo.dev/bestplay?mode=0')
        resp.raise_for_status()
        top_plays = resp.json()

    def get_access_token(self):
        resp = requests.post("https://id.twitch.tv/oauth2/token", params={"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "client_credentials"})
        resp.raise_for_status()
        resp = resp.json()
        return resp['access_token'], resp['expires_in']

    def get_stream_status(self):
        try:
            resp = requests.get("https://api.twitch.tv/helix/search/channels", params={"query": self.channel_to_run_in, "first": 1}, headers={"Authorization": f"Bearer {self.access_token}", "Client-Id": self.client_id})
            resp.raise_for_status()
            resp = resp.json()
            self.offline = not resp['data'][0]['is_live']
        except:
            print(traceback.format_exc())
            self.offline = False

    # Fundamental

    async def start(self):
        async with websockets.connect(self.uri) as ws:
            self.ws = ws
            self.running = True

            try:
                await self.connect()  # Connect to the irc server
                poll = asyncio.run_coroutine_threadsafe(self.poll(), self.loop)  # Begin polling for events sent by the server
                await asyncio.sleep(5)  # Leave time for reply from server before beginning to join channels and stuff
                await self.run()  # Join channels + whatever else is in the function

                last_check = perf_counter() - 20
                last_ping = perf_counter() - 60*60  # 1 hour
                while self.running:
                    await asyncio.sleep(1)  # Leave time for other threads to run

                    # Check is ed is live
                    if perf_counter() - last_check >= 20:
                        self.get_stream_status()
                        last_check = perf_counter()

                    # Check if access token needs to be renewed
                    if perf_counter() >= self.expire_time:
                        self.access_token, self.expire_time = self.get_access_token()
                        self.expire_time += perf_counter()

                    # Ping database once an hour for keepalive
                    if perf_counter() - last_ping >= 60*60:
                        self.database.ping()

                    # Check all future objects and if they're done: print the result and remove them from the list
                    for future in self.future_objects:
                        if future.done():
                            try:
                                result = future.result()
                                if result is not None:
                                    print(future.result())
                            except:
                                print(traceback.format_exc())
                            finally:
                                self.future_objects.remove(future)

                    # Check if poll is no longer running, in which case, the bot is no longer running.
                    if poll.done():
                        print(poll.result())
                        self.running = False

            except KeyboardInterrupt:
                pass
            except websockets.exceptions.ConnectionClosedError as e:
                # Restart the bot
                print(e)
                if self.restarts < 5:
                    self.restarts += 1
                    print("Restarting bot...")
                    await self.start()
            except:
                print(traceback.format_exc())
            finally:
                self.running = False

    async def run(self):
        # await self.register_cap("tags")  # Not using atm
        await self.join(self.channel_to_run_in)
        if not TESTING:
            await self.join(self.username)

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
            ctx = Context.from_string(data)

            if ctx.message_type == MessageType.PRIVMSG:
                # Run in its own thread to avoid holding up the polling thread
                future = asyncio.run_coroutine_threadsafe(self.on_message(ctx), self.loop)
                self.future_objects.append(future)

    async def join(self, channel):
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
        if not self.offline and channel == self.channel_to_run_in:
            return
        await self.message_lock.acquire()
        await self.ws.send(f"PRIVMSG #{channel} :/me {message}")
        print(f"> PRIVMSG #{channel} :{message}")
        await asyncio.sleep(1.5)  # Wait 1.5 seconds before releasing lock to avoid going over rate limits
        self.message_lock.release()

    # Events

    async def on_message(self, ctx):
        if (not self.offline and ctx.channel == self.channel_to_run_in) or ctx.user == self.username:
            return

        message = ctx.message
        if message.lower().startswith("pogpega") and message.lower() != "pogpega":
            message = ctx.message[8:]

        if message.startswith("Use code"):
            await asyncio.sleep(1)
            await self.send_message(ctx.channel, "PogU 👆 Use code \"BTMC\" !!!")
        elif message.strip() in [str(num) for num in range(1, 5)] and self.trivia_diff is not None:
            message = int(message)
            if message in self.guessed_answers:
                return
            await self.on_answer(ctx, message)
            return

        for scramble_type, scramble in self.scrambles.items():
            if scramble.in_progress:
                await self.on_scramble(ctx, scramble_type)

        if self.bomb_party_helper.started:
            await self.on_bomb_party(ctx)

        await self.on_afk(ctx)

        if message.startswith("!"):
            command = message.split()[0].lower().replace("!", "")
            args = message.split()[1:]
            if command in self.commands:
                await self.commands[command](ctx)

    # Commands

    @cooldown(cmd_cd=1, user_cd=2)
    async def pull(self, ctx):
        # TODO: Try and make this look more clean
        user = ctx.user
        if user not in self.pity:
            self.pity.update({user: {4: 0, 5: 0}})
            self.database.new_pity(user, 0, 0)

        pity = False
        self.pity[user][4] += 1
        self.pity[user][5] += 1
        if self.pity[user][4] == 10 and self.pity[user][5] != 90:
            pull = 4
            pity = True
        elif self.pity[user][5] == 90:
            pull = 5
            pity = True
        else:
            num = random.randint(1, 1000)
            pull = 3
            if num <= 6:
                pull = 5
            elif num <= 57:
                pull = 4
        await self.send_message(ctx.channel,
                                f"@{user} You pulled {random.choice(self.pull_options[str(pull)])} " +
                                ("\u2B50\u2B50\u2B50" if pull == 3 else '🌟' * pull) +
                                {3: ". 😔", 4: "! Pog", 5: "! PogYou"}[pull] +
                                ((" Rolls in: " + str(
                                    self.pity[user][pull] if not pity else {4: 10, 5: 90}[pull])) if pull != 3 else "")
                                )
        if pull == 5:
            self.pity[user][5] = 0
            self.pity[user][4] = 0
        elif pull == 4:
            self.pity[user][4] = 0
        self.database.save_pity(user, self.pity[user][4], self.pity[user][5])

    @cooldown()
    async def font(self, ctx):
        args = ctx.get_args()
        if len(args) < 2:
            return await self.send_message(ctx.channel, "Must provide a font name and characters to convert. Do !fonts to see a list of valid fonts.")

        font_name = args[0].lower()
        if font_name not in fonts:
            return await self.send_message(ctx.channel, f"{font_name} is not a valid font name.")

        await self.send_message(ctx.channel, "".join([fonts[font_name][layout.index(char)] if char in layout else char for char in " ".join(args[1:])]))

    @cooldown()
    async def fonts(self, ctx):
        await self.send_message(ctx.channel, f'Valid fonts: {", ".join(list(fonts.keys()))}.')

    @cooldown(user_cd=5, cmd_cd=3)
    async def guess(self, ctx):
        args = ctx.get_args()
        if len(args) < 1:
            return await self.send_message(ctx.channel, f"@{ctx.user} You must provide a number 1-1000 to guess with")

        if not args[0].isdigit():
            return await self.send_message(ctx.channel, f"@{ctx.user} That's not a valid number OuttaPocket Tssk")

        guess = int(args[0])

        if self.number == guess:
            await self.send_message(ctx.channel, f"@{ctx.user} You got it PogYou")
            self.number = random.randint(1, 1000)
        else:
            await self.send_message(ctx.channel, f"@{ctx.user} It's not {guess}. Try guessing " + (
                "higher" if guess < self.number else "lower") + ". veryPog")

    # TODO: consider putting trivia stuff in its own class

    @cooldown()
    async def trivia(self, ctx):
        # TODO: get this working again
        if self.answer is not None:
            return
        self.answer = "temp"
        difficulty = {
            "easy": "EZ",
            "medium": "monkaS",
            "hard": "pepeMeltdown"
        }
        args = ctx.get_args()
        resp = requests.get(f"https://opentdb.com/api.php?amount=1&type=multiple{f'&category={args[0]}' if len(args) > 0 else ''}").json()['results'][0]

        answers = [resp['correct_answer']] + resp['incorrect_answers']
        random.shuffle(answers)
        self.answer = answers.index(resp['correct_answer']) + 1
        answer_string = " ".join([html.unescape(f"[{i + 1}] {answers[i]} ") for i in range(len(answers))])
        self.trivia_diff = resp['difficulty']

        await self.send_message(ctx.channel,
                                f"Difficulty: {resp['difficulty']} {difficulty[resp['difficulty']]} "
                                f"Category: {resp['category']} veryPog "
                                f"Question: {html.unescape(resp['question'])} monkaHmm "
                                f"Answers: {answer_string}")
        self.trivia_future = self.set_timed_event(20, self.on_trivia_finish, ctx.channel)
        self.trivia_future.add_done_callback(future_callback)

    @requires_gamba_data
    async def on_answer(self, ctx, answer):
        self.guessed_answers.append(answer)
        worth = self.trivia_info[self.trivia_diff]
        if answer == self.answer:
            await self.send_message(ctx.channel, f"@{ctx.user} {answer} is the correct answer ✅. You gained {worth * (self.trivia_info['decrease'] ** (len(self.guessed_answers) - 1))} Becky Bucks 5Head Clap")
            self.gamba_data[ctx.user]['money'] += worth * (self.trivia_info['decrease'] ** (len(self.guessed_answers) - 1))
            self.save_money(ctx.user)
            await self.on_trivia_finish(ctx.channel, timeout=False)
        else:
            await self.send_message(ctx.channel, f"@{ctx.user} {answer} is wrong ❌. You lost {worth*self.trivia_info['penalty']} Becky Bucks 3Head Clap")
            self.gamba_data[ctx.user]['money'] -= worth*self.trivia_info['penalty']
            self.save_money(ctx.user)
            if self.answer not in self.guessed_answers and len(self.guessed_answers) == 3:
                self.trivia_diff = None  # make sure someone doesn't answer before it can say no one got it right
                await self.send_message(ctx.channel, f"No one answered correctly! The answer was {self.answer}.")
                await self.on_trivia_finish(ctx.channel, timeout=False)

    async def on_trivia_finish(self, channel, timeout=True):
        if timeout:
            await self.send_message(channel, f"Time has run out for the trivia! The answer was {self.answer}.")
        else:
            self.trivia_future.cancel()
        self.answer = None
        self.guessed_answers = []
        self.trivia_diff = None
        self.trivia_future = None

    @cooldown()
    async def slap(self, ctx):
        args = ctx.get_args()
        if not args:
            return await self.send_message(ctx.channel, "You must provide a user to slap.")

        hit = random.choice((True, False))
        await self.send_message(ctx.channel,
                                f"{ctx.user} slapped {args[0]}! D:" if hit else f"{ctx.user} tried to slap {args[0]}, but they caught it! pepePoint")

    @cooldown(cmd_cd=3)
    async def pity(self, ctx):
        if ctx.user not in self.pity:
            return await self.send_message(ctx.channel, "You haven't rolled yet (from the time the bot started up).")
        await self.send_message(ctx.channel, f"@{ctx.user} 4* pity in {10 - self.pity[ctx.user][4]} rolls; "
                                             f"5* pity in {90 - self.pity[ctx.user][5]} rolls.")

    async def scramble(self, ctx, scramble_type):
        if self.scramble_manager.in_progress(scramble_type):
            return

        scrambled_word = self.scramble_manager.get_scramble(scramble_type, ctx.channel)
        await self.send_message(ctx.channel, f"Unscramble this "
                                             f"{self.scramble_manager.get_scramble_name(scramble_type)}: "
                                             f"{scrambled_word.lower()}")
        future = self.set_timed_event(120, self.on_scramble_finish, ctx.channel, scramble_type)
        future.add_done_callback(future_callback)
        self.scramble_manager.pass_future(scramble_type, future)

    async def on_scramble(self, ctx, scramble_type):
        money = self.scramble_manager.check_answer(scramble_type, ctx.message)
        if money is None:
            return
        answer = self.scramble_manager.get_answer(scramble_type)
        name = self.scramble_manager.get_scramble_name(scramble_type)
        self.scramble_manager.reset(scramble_type)
        await self.send_message(ctx.channel,
                                f"@{ctx.user} You got it right! "
                                f"{answer} was the "
                                f"{name}. "
                                f"Drake You've won {money} Becky Bucks!")
        if ctx.user not in self.gamba_data:
            self.add_new_user(ctx.user)
        self.gamba_data[ctx.user]["money"] += money
        self.save_money(ctx.user)

    @cooldown(cmd_cd=5)
    async def hint(self, ctx, scramble_type):
        if not self.scramble_manager.hints_left(scramble_type):
            return await self.send_message(ctx.channel, f"@{ctx.user} There are no hints left bruh")
        await self.send_message(ctx.channel,
                                f"Here's a hint "
                                f"({self.scramble_manager.get_scramble_name(scramble_type)}): "
                                f"{self.scramble_manager.get_hint(scramble_type).lower()}")

    async def on_scramble_finish(self, channel, scramble_type):
        await self.send_message(channel,
                                f"Time is up! "
                                f"The {self.scramble_manager.get_scramble_name(scramble_type)} "
                                f"was {self.scramble_manager.get_answer(scramble_type)}")
        self.scramble_manager.reset(scramble_type)

    def add_new_user(self, user):
        self.gamba_data.update({user: {
            'money': 0,
            'settings': {
                'receive': True
            }
        }})
        self.database.new_user(user)

    @cooldown(user_cd=60)
    @requires_gamba_data
    async def collect(self, ctx):
        money = random.randint(10, 100)
        self.gamba_data[ctx.user]["money"] += money
        await self.send_message(ctx.channel, f"@{ctx.user} You collected {money} Becky Bucks!")
        self.save_money(ctx.user)

    @cooldown(cmd_cd=2, user_cd=3)
    @requires_gamba_data
    async def gamba(self, ctx):
        args = ctx.get_args()
        if not args:
            return await self.send_message(ctx.channel,
                                           f"@{ctx.user} You must provide an amount to bet and a risk factor. Do !riskfactor to learn more")
        if len(args) < 2:
            return await self.send_message(ctx.channel,
                                           f"@{ctx.user} You must also provide a risk factor. Do !riskfactor to learn more.")

        if args[0].lower() == "all":
            args[0] = self.gamba_data[ctx.user]['money']
        try:
            amount = float(args[0])
            risk_factor = int(args[1])
        except ValueError:
            return await self.send_message(ctx.channel,
                                           f"@{ctx.user} You must provide a valid number (integer for risk factor) value.")
        if risk_factor not in range(1, 100):
            return await self.send_message(ctx.channel, f"@{ctx.user} The risk factor you provided is outside the range 1-99!")
        if amount > self.gamba_data[ctx.user]["money"]:
            return await self.send_message(ctx.channel, f"@{ctx.user} You don't have enough Becky Bucks to bet that much!")
        if amount == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user} You can't bet nothing bruh")
        if amount < 0:
            return await self.send_message(ctx.channel, f"@{ctx.user} Please specify a positive integer bruh")

        loss = random.randint(1, 100) in range(risk_factor)
        if loss:
            await self.send_message(ctx.channel, f"@{ctx.user} YIKES! You lost {amount} Becky Bucks ❌ [LOSE]")
            self.gamba_data[ctx.user]["money"] -= amount
        else:
            payout = round((1 + risk_factor * 0.01) * amount - amount, 2)
            await self.send_message(ctx.channel, f"@{ctx.user} You gained {payout} Becky Bucks! ✅ [WIN]")
            self.gamba_data[ctx.user]["money"] += payout
        self.gamba_data[ctx.user]["money"] = round(self.gamba_data[ctx.user]["money"], 2)
        self.save_money(ctx.user)

    @cooldown()
    async def risk_factor(self, ctx):
        await self.send_message(ctx.channel,
                                f"@{ctx.user} The risk factor determines your chances of losing the bet and your payout. "
                                f"The chance of you winning the bet is 100 minus the risk factor. "
                                f"Your payout is (1 + riskfactor*0.01)) * amount bet "
                                f"(basically says more risk = better payout)")

    @cooldown(user_cd=10)
    @requires_gamba_data
    async def balance(self, ctx):
        args = ctx.get_args()
        user_to_check = ctx.user
        if args:
            user_to_check = args[0].replace("@", "").lower()
        if user_to_check not in self.gamba_data:
            user_to_check = ctx.user
        await self.send_message(ctx.channel, f"{user_to_check} currently has {round(self.gamba_data[user_to_check]['money'])} Becky Bucks.")

    @cooldown()
    async def leaderboard(self, ctx):
        lead = {k: v for k, v in sorted(self.gamba_data.items(), key=lambda item: item[1]['money'])}
        top_users = list(lead.keys())[-5:]
        top_money = list(lead.values())[-5:]
        output = "Top 5 richest users: "
        for i in range(5):
            output += f'{i + 1}. {top_users[4 - i]}_${round(top_money[4 - i]["money"], 2)} '
        await self.send_message(ctx.channel, output)

    @cooldown()
    @requires_gamba_data
    async def get_ranking(self, ctx):
        lead = {k: v for k, v in sorted(self.gamba_data.items(), key=lambda item: item[1]['money'])}
        users = list(lead.keys())
        users.reverse()
        rank = users.index(ctx.user) + 1
        await self.send_message(ctx.channel, f"@{ctx.user} You are currently rank {rank} in terms of Becky Bucks!")

    @cooldown()
    async def filter(self, ctx):
        await self.send_message(ctx.channel,
                                "Here's a filter that applies to me and any user that uses my commands: https://pastebin.com/nyBX5jbb")

    @cooldown()
    @requires_gamba_data
    async def give(self, ctx):
        args = ctx.get_args()
        user_to_give = args[0].lower()
        if user_to_give not in self.gamba_data:
            return await self.send_message(ctx.channel, f"@{ctx.user} That's not a valid user to give money to.")
        if not self.gamba_data[user_to_give]['settings']['receive']:
            return await self.send_message(ctx.channel,
                                           f"@{ctx.user} This user has their receive setting turned off and therefore cannot accept money.")
        amount = args[1]
        try:
            amount = round(float(amount), 2)
        except ValueError:
            return await self.send_message(ctx.channel, f"@{ctx.user} That's not a valid number.")
        if self.gamba_data[ctx.user]['money'] < amount:
            return await self.send_message(ctx.channel, f"@{ctx.user} You don't have that much money to give.")

        if amount < 0:
            return await self.send_message(ctx.channel, "You can't give someone a negative amount OuttaPocket Tssk")

        self.gamba_data[ctx.user]['money'] -= amount
        self.gamba_data[user_to_give]['money'] += amount
        await self.send_message(ctx.channel, f"@{ctx.user} You have given {user_to_give} {amount} Becky Bucks!")
        self.save_money(ctx.user)
        self.save_money(user_to_give)

    @cooldown()
    @requires_gamba_data
    async def toggle(self, ctx):
        args = ctx.get_args()
        if len(args) < 2:
            return await self.send_message(ctx.channel, f"@{ctx.user} You must provide a setting name and either on or off")
        setting = args[0].lower()
        if setting not in self.gamba_data[ctx.user]['settings']:
            return await self.send_message(ctx.channel,
                                           f"@{ctx.user} That's not a valid setting name. The settings consist of the following: " + ", ".join(
                                               list(self.gamba_data[ctx.user]['settings'].keys())))
        try:
            value = {"on": True, "off": False}[args[1].lower()]
        except KeyError:
            return await self.send_message(ctx.channel, "You must specify on or off.")

        self.gamba_data[ctx.user]['settings'][setting] = value
        self.database.update_userdata(ctx.user, setting, value)
        await self.send_message(ctx.channel, f"@{ctx.user} The {setting} setting has been turned {args[1]}.")

    @requires_dev
    async def market_balance(self, ctx):
        lead = {k: v for k, v in sorted(self.gamba_data.items(), key=lambda item: item[1]['money'])}
        top_user = list(lead.keys())[-1]
        pool = self.gamba_data[top_user]['money']
        giveaway = round(pool / len(self.gamba_data), 2)
        self.gamba_data[top_user]['money'] = 0
        self.save_money(top_user)
        for user in self.gamba_data:
            self.gamba_data[user]['money'] += giveaway
            self.save_money(user)

        await self.send_message(ctx.channel,
                                f"I have given away {giveaway} Becky Bucks to each player provided by {top_user} without their consent PogU")

    @cooldown(user_cd=5, cmd_cd=3)
    @requires_gamba_data
    async def rps(self, ctx):
        args = ctx.get_args()
        if not args:
            return await self.send_message(ctx.channel, f"@{ctx.user} You must say either rock, paper, or scissors. "
                                                        f"(You can also use the first letter for short)")
        choice = args[0][0].lower()
        if choice not in ('r', 'p', 's'):
            return await self.send_message(ctx.channel, f"@{ctx.user} That's not a valid move. You must say either rock, paper, or scissors. "
                                                        f"(You can also use the first letter for short)")

        com_choice = random.choice(('r', 'p', 's'))
        win = {"r": "s", "s": "p", "p": "r"}
        abbr = {"r": "rock", "s": "scissors", "p": "paper"}
        if com_choice == choice:
            return await self.send_message(ctx.channel, f"@{ctx.user} I also chose {abbr[com_choice]}! bruh")
        if win[com_choice] == choice:
            await self.send_message(ctx.channel, f"@{ctx.user} LETSGO I won, {abbr[com_choice]} beats {abbr[choice]}. You lose 10 Becky Bucks!")
            self.gamba_data[ctx.user]['money'] -= 10
            return self.save_money(ctx.user)
        await self.send_message(ctx.channel, f"@{ctx.user} IMDONEMAN I lost, {abbr[choice]} beats {abbr[com_choice]}. You win 10 Becky Bucks!")
        self.gamba_data[ctx.user]['money'] += 10
        self.save_money(ctx.user)
        
    @requires_dev
    async def new_name(self, ctx):
        # TODO: save to db
        args = ctx.get_args()
        old_name = args[0]
        new_name = args[1]
        if old_name not in self.gamba_data or new_name not in self.gamba_data:
            return await self.send_message(ctx.channel, "One of the provided names is not valid.")
        self.gamba_data[old_name]['money'] += self.gamba_data[new_name]['money']
        self.gamba_data[new_name] = dict(self.gamba_data[old_name])
        del self.gamba_data[old_name]
        await self.send_message(ctx.channel, f"@{ctx.user} The data has been updated for the new name!")
        self.database.delete_user(old_name)
        self.save_money(new_name)
        for setting, val in self.gamba_data[new_name]["settings"].items():
            self.database.update_userdata(new_name, setting, val)

    @cooldown()
    async def scramble_difficulties(self, ctx):
        await self.send_message(ctx.channel,
                                f"@{ctx.user} Difficulty multiplier for each scramble: "
                                "%s" % ', '.join(
                                    ['%s-%s' % (identifier, scramble.difficulty_multiplier)
                                     for identifier, scramble in self.scrambles.items()])
                                )

    @cooldown()
    async def scramble_calc(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user} Scramble payout is calculated by picking a random number 5-10, "
                                             f"multiplying that by the length of the word (excluding spaces), multiplying "
                                             f"that by hint reduction, and multiplying that by the scramble difficulty "
                                             f"multiplier for that specific scramble. To see the difficulty multipliers, "
                                             f"do !scramble_multiplier. Hint reduction is the length of the word minus the "
                                             f"amount of hints used divided by the length of the word.")

    @cooldown()
    async def fact(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user} {random.choice(self.facts)}")

    @cooldown()
    async def afk(self, ctx):
        args = ctx.get_args()
        await self.send_message(ctx.channel, f"@{ctx.user} Your afk has been set.")
        message = " ".join(args)
        self.afk[ctx.user] = {"message": message, "time": datetime.now().isoformat()}
        self.database.save_afk(ctx.user, message)

    @cooldown()
    async def help_command(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user} sheepposubot help (do !commands for StreamElements): https://sheep.sussy.io/index.html (domain kindly supplied by pancakes man)")

    async def on_afk(self, ctx):
        pings = [word.replace("@", "").replace(",", "").replace(".", "").replace("-", "") for word in ctx.message.lower().split() if word.startswith("@")]
        for ping in pings:
            if ping in self.afk:
                await self.send_message(ctx.channel,  f"@{ctx.user} {ping} is afk "
                                                      f"({format_date(datetime.fromisoformat(self.afk[ping]['time']))} ago): "
                                                      f"{self.afk[ping]['message']}")

        if ctx.user not in self.afk:
            return
        elif (datetime.now() - datetime.fromisoformat(self.afk[ctx.user]['time'])).seconds > 60:
            await self.send_message(ctx.channel, f"@{ctx.user} Your afk has been removed.")
            del self.afk[ctx.user]
            self.database.delete_afk(ctx.user)

    @cooldown()
    async def trivia_category(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user} I'll make something more intuitive later but for now, "
                                             f"if you want to know which number correlates to which category, "
                                             f"go here https://opentdb.com/api_config.php, click a category, "
                                             f"click generate url and then check the category specified in the url.")

    @cooldown()
    async def sourcecode(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user} https://github.com/Sheepposu/offlinechatbot")

    # Bomb party functions
    @cooldown()
    async def bomb_party(self, ctx):
        if self.bomb_party_helper.in_progress:
            return
        self.bomb_party_helper.add_player(ctx.user)
        self.bomb_party_helper.on_in_progress()

        await self.send_message(ctx.channel, f"{ctx.user} has started a Bomb Party game! Anyone else who wants to play should type !join. When enough players have joined, the host should type !start to start the game, otherwise the game will automatically start or close after 2 minutes.")
        self.bomb_party_future = self.set_timed_event(120, self.close_or_start_game, ctx.channel)
        self.bomb_party_future.add_done_callback(future_callback)

    async def close_or_start_game(self, channel):
        if not self.bomb_party_helper.can_start:
            self.close_bomb_party()
            return await self.send_message(channel, "The bomb party game has closed since there is only one player in the party.")
        await self.start_bomb_party(Context(user="", channel=channel), False)

    async def start_bomb_party(self, ctx, cancel=True):
        if not self.bomb_party_helper.in_progress or \
                self.bomb_party_helper.started or \
                ctx.user != self.bomb_party_helper.host:
            return
        if not self.bomb_party_helper.can_start:
            return await self.send_message(ctx.channel, f"@{ctx.user} You need at least 2 players to start the bomb party game.")
        if cancel:
            self.bomb_party_future.cancel()

        self.bomb_party_helper.on_start()
        self.bomb_party_helper.set_letters()

        await self.send_message(ctx.channel, f"@{self.bomb_party_helper.current_player} You're up first! Your string of letters is {self.bomb_party_helper.current_letters}")
        self.bomb_party_future = self.set_timed_event(self.bomb_party_helper.starting_time, self.bomb_party_timer, ctx.channel)
        self.bomb_party_future.add_done_callback(future_callback)

    @cooldown(user_cd=10, cmd_cd=0)
    async def join_bomb_party(self, ctx):
        if not self.bomb_party_helper.in_progress or self.bomb_party_helper.started:
            return
        if ctx.user in self.bomb_party_helper.party:
            return await self.send_message(ctx.channel, f"@{ctx.user} You have already joined the game")

        self.bomb_party_helper.add_player(ctx.user)
        await self.send_message(ctx.channel, f"@{ctx.user} You have joined the game of bomb party!")

    @cooldown(cmd_cd=0)
    async def leave_bomb_party(self, ctx):
        if ctx.user not in self.bomb_party_helper.party:
            return
        self.bomb_party_helper.remove_player(ctx.user)
        await self.send_message(ctx.channel, f"@{ctx.user} You have left the game of bomb party.")
        if self.bomb_party_helper.started and await self.check_win(ctx.channel):
            if self.bomb_party_future is not None:
                self.bomb_party_future.cancel()
        elif self.bomb_party_helper.current_player == ctx.user:
            if self.bomb_party_future is not None:
                self.bomb_party_future.cancel()
            await self.next_player(ctx.channel)
        elif self.bomb_party_helper.in_progress and not self.bomb_party_helper.started:
            if len(self.bomb_party_helper.party) == 0:
                self.close_bomb_party()
                await self.send_message(ctx.channel, "The game of bomb party has closed.")

    @cooldown(user_cd=0, cmd_cd=0)
    async def change_bomb_settings(self, ctx):
        if not self.bomb_party_helper.in_progress or \
                self.bomb_party_helper.started or \
                self.bomb_party_helper.host != ctx.user:
            return
        args = ctx.message.content.split()
        if len(args) < 2:
            return await self.send_message(ctx.channel, f"@{ctx.user} You must provide a setting name and the value: "
                                                        f"!settings <setting> <value>. Valid settings: "
                                                        f"{self.bomb_party_helper.valid_settings_string}")
        setting = args[0].lower()
        value = args[1].lower()
        return_msg = self.bomb_party_helper.set_setting(setting, value)
        await self.send_message(ctx.channel, f"@{ctx.user} {return_msg}")

    @cooldown()
    async def player_list(self, ctx):
        if not self.bomb_party_helper.in_progress:
            return
        await self.send_message(ctx.channel, f"@{ctx.user} Current players playing bomb party: {', '.join(self.bomb_party_helper.player_list)}")

    async def bomb_party_timer(self, channel):
        msg = self.bomb_party_helper.on_explode()
        await self.send_message(channel, msg)
        if await self.check_win(channel):
            return
        await self.next_player(channel)

    async def next_player(self, channel):
        self.bomb_party_helper.next_player()
        self.bomb_party_helper.set_letters()
        player = self.bomb_party_helper.current_player
        await self.send_message(channel, f"@{player} Your string of letters is {self.bomb_party_helper.current_letters} - "
                                         f"You have {round(self.bomb_party_helper.seconds_left)} seconds.")
        self.bomb_party_future = self.set_timed_event(self.bomb_party_helper.seconds_left, self.bomb_party_timer, channel)
        self.bomb_party_future.add_done_callback(future_callback)

    async def on_bomb_party(self, ctx):
        if ctx.user != self.bomb_party_helper.current_player.user:
            return
        if ctx.message not in self.all_words:
            return
        return_msg = self.bomb_party_helper.check_message(ctx.message)
        if return_msg is not None:
            return await self.send_message(ctx.channel, f"@{self.bomb_party_helper.current_player} {return_msg}")
        self.bomb_party_future.cancel()
        self.bomb_party_helper.on_word_used(ctx.message)
        await self.next_player(ctx.channel)

    async def check_win(self, channel):
        winner = self.bomb_party_helper.get_winner()
        print(winner)
        if winner is None:
            return False
        winner = winner.user
        if winner not in self.gamba_data:
            self.add_new_user(winner)
        money = self.bomb_party_helper.winning_money
        self.gamba_data[winner]['money'] += money
        self.save_money(winner)
        self.close_bomb_party()
        await self.send_message(channel, f"@{winner} Congratulations on winning the bomb party game! You've won {money} Becky Bucks!")
        return True

    def close_bomb_party(self):
        self.bomb_party_future.cancel()
        self.bomb_party_future = None
        self.bomb_party_helper.on_close()

    @cooldown(cmd_cd=2, user_cd=0)
    async def random_fact(self, ctx):
        fact = requests.get("https://uselessfacts.jsph.pl/random.json?language=en")
        fact.raise_for_status()
        await self.send_message(ctx.channel, f"Fun fact: {fact.json()['text']}")

    @requires_dev
    async def reload_from_db(self, ctx):
        self.load_db_data()
        await self.send_message(ctx.channel, f"@{ctx.user} Local data has been reloaded from database.")

    @requires_dev
    async def refresh_emotes(self, ctx):
        self.load_emotes()
        await self.send_message(ctx.channel, f"@{ctx.user} Emotes have been reloaded.")


bot = Bot()
bot.running = True
bot.loop.run_until_complete(bot.start())
