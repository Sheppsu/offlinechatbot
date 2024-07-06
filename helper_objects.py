from __future__ import annotations

import json
import random

import osu
import requests
import html
import math
import asyncio
import rosu_pp_py as rosu
import beatmap_reader as br
from time import monotonic
from enum import IntEnum, IntFlag
from collections import namedtuple
from constants import admins
from aiohttp import ClientSession, client_exceptions


class BombPartyPlayer:
    def __init__(self, user, lives):
        self.user = user
        self.lives = lives

    @property
    def dead(self):
        return self.lives == 0

    def __str__(self):
        return f"{self.user} ({'♥'*self.lives})"


class BombParty:
    valid_bomb_settings = {
        "difficulty": ("easy", "medium", "hard", "nightmare", "impossible"),
        "timer": range(5, 60 + 1),
        "minimum_time": range(0, 10 + 1),
        "lives": range(1, 5 + 1),
    }

    def __init__(self, init=True):
        if init:
            self.bomb_party_letters = self.construct_bomb_party_letters()
            self.bomb_setting_functions = {
                "lives": self.on_lives_set,
            }

        self.in_progress = False
        self.started = False
        self.used_words = []
        self.party = {}
        self.current_player_index = 0
        self.current_letters = ""
        self.bomb_start_time = 0
        self.turn_order = []
        self.timer = 30
        self.bomb_settings = self.default_settings

    @property
    def default_settings(self):
        return {
            "difficulty": "medium",
            "timer": 30,
            "minimum_time": 5,
            "lives": 3,
        }

    def set_default_values(self):
        self.__init__(init=False)

    @staticmethod
    def construct_bomb_party_letters():
        with open("data/2strings.json", "r") as f:
            letters = json.load(f)
            with open("data/3strings.json", "r") as f3:
                letters.update(json.load(f3))

            return {
                "easy": [let for let, amount in letters.items() if amount >= 10000 and '-' not in let],
                "medium": [let for let, amount in letters.items() if 10000 > amount >= 5000 and '-' not in let],
                "hard": [let for let, amount in letters.items() if
                         5000 > amount >= 1000 or (amount >= 5000 and '-' in let)],
                "nightmare": [let for let, amount in letters.items() if 1000 > amount >= 500],
                "impossible": [let for let, amount in letters.items() if 500 > amount],
            }

    def add_player(self, user):
        if user not in self.party:
            self.party.update({user: BombPartyPlayer(user, self.bomb_settings['lives'])})

    def remove_player(self, user):
        if user in self.party:
            del self.party[user]
            if self.started:
                self.turn_order.remove(user)

    def on_in_progress(self):
        self.in_progress = True

    def on_start(self):
        self.turn_order = list(self.party.keys())
        random.shuffle(self.turn_order)
        self.timer = self.bomb_settings['timer']
        self.bomb_start_time = monotonic()
        self.started = True

    def on_word_used(self, message):
        message = message.lower()
        self.timer -= max((0, monotonic() - self.bomb_start_time - self.bomb_settings['minimum_time']))
        self.used_words.append(message)

    def on_explode(self):
        print("setting timer")
        self.timer = self.bomb_settings['timer']
        print("bomb start time to zero")
        self.bomb_start_time = 0
        print("player loses life")
        player = self.current_player
        player.lives -= 1
        print("return message")
        return f"@{player.user} " + \
               (f"You ran out of time and now have {player.lives} {'♥' * player.lives} heart(s) left"
                if player.lives != 0 else "You ran out of time and lost all your lives! YouDied")

    def on_close(self):
        self.set_default_values()

    def next_player(self):
        player = self.current_player.user
        while self.current_player.lives == 0 or self.current_player.user == player:
            self.current_player_index = 1 + self.current_player_index if self.current_player_index != len(self.turn_order) - 1 else 0
        self.bomb_start_time = monotonic()

    def set_letters(self):
        self.current_letters = random.choice(self.bomb_party_letters[self.bomb_settings['difficulty']])

    def get_winner(self):
        print("getting winner")
        players_left = [player for player in self.party.values() if player.lives != 0]
        print("returning winner")
        return players_left[0] if len(players_left) == 1 else None

    def set_setting(self, setting, value):
        if setting not in self.bomb_settings:
            return f"That's not a valid setting. Valid settings: {', '.join(list(self.bomb_settings.keys()))}"
        try:
            value = type(self.bomb_settings[setting])(value)
            if value not in self.valid_bomb_settings[setting]:
                return "That's not a valid value for this setting."
            self.bomb_settings[setting] = value
            if setting in self.bomb_setting_functions:
                self.bomb_setting_functions[setting]()
            return f"The {setting} setting has been changed to {value}"
        except ValueError:
            return "There was a problem processing the value you gave for the specific setting."

    def on_lives_set(self):
        for player in self.party:
            self.party[player].lives = self.bomb_settings['lives']

    def check_message(self, message):
        message = message.lower()
        if message in self.used_words:
            return "That word has already been used."
        if self.current_letters not in message:
            return f"That word does not contain your string of letters: {self.current_letters}"
        if len(message) == len(self.current_letters):
            return "You cannot answer with the string of letters itself."

    def get_overall_multiplier(self):
        defaults = self.default_settings
        difficulties = self.valid_bomb_settings["difficulty"]
        return difficulties.index(defaults["difficulty"])/difficulties.index(self.bomb_settings["difficulty"])

    @property
    def current_player(self):
        if len(self.turn_order) == 0:
            return None
        return self.party[self.turn_order[self.current_player_index]]

    @property
    def player_list(self):
        return list(self.party.values())

    @property
    def can_start(self):
        return len(self.party) >= 2

    @property
    def host(self):
        return list(self.party.keys())[0]

    @property
    def winning_money(self):
        return (len(self.party)-1) * 100

    @property
    def seconds_left(self):
        return self.timer+self.bomb_settings['minimum_time']

    @property
    def starting_time(self):
        return self.timer + self.bomb_settings['minimum_time']

    @property
    def valid_settings_string(self):
        return ", ".join(list(self.valid_bomb_settings.keys()))


class ScrambleHintType(IntEnum):
    DEFAULT = 0
    EVERY_OTHER = 1


class ScrambleRewardType(IntEnum):
    LINEAR = 0
    LOGARITHM = 1


class ScrambleRewardCalculator:
    @classmethod
    def calculate(cls, reward_type, hint, multiplier=1):
        if reward_type == ScrambleRewardType.LINEAR:
            return cls.linear(hint, multiplier)
        return cls.logarithm(hint, multiplier)

    @classmethod
    def linear(cls, hint, multiplier=1):
        return round(
            random.randint(5, 10) *
            hint.count("?") *
            multiplier
        )

    @classmethod
    def logarithm(cls, hint, multiplier=1):
        return round(
            random.randint(10, 15) *
            math.log2(hint.count("?") ) *
            multiplier
        )


class Scramble:
    banned_words = [
        # Was originally used to stop this word from being posted for scramble,
        # but since there's a new list with non-tos words it doesn't really do anything
        "kike"
    ]

    def __init__(self, name, answer_generator, difficulty_multiplier=1, hint_type=ScrambleHintType.DEFAULT,
                 case_sensitive=False, reward_type=ScrambleRewardType.LINEAR):
        self.name = name
        self.difficulty_multiplier = difficulty_multiplier
        self.hint_type = hint_type
        self.case_sensitive = case_sensitive
        self.reward_type = reward_type

        self.progress = {}

        self.generate_answer = answer_generator

    def reset(self, channel, cancel=True):
        future = self.progress[channel]["future"]
        self.progress[channel] = self.default_progress
        if cancel and future is not None and not future.cancelled() and not future.done():
            print(f"Cancelling future for {self.name} scramble")
            future.cancel()

    def new_answer(self, channel):
        if channel not in self.progress:
            self.progress.update({channel: self.default_progress})
        progress = self.progress[channel]

        args = []
        if self.generate_answer.__code__.co_argcount > 0:  # Check whether it takes the channel arg
            args.append(channel)
        progress["answer"] = self.generate_answer(*args)

        count = 0
        while progress["answer"] in self.banned_words:
            progress["answer"] = self.generate_answer(*args)
            count += 1
            if count > 100:  # Just in case ig
                raise Exception("Could not generate an unbanned answer")
        progress["hint"] = "?" * len(progress["answer"])

    def update_hint(self, channel):
        getattr(self, f"{self.hint_type.name.lower()}_hint")(channel)
        return self.progress[channel]["hint"]

    def default_hint(self, channel):
        hint = self.progress[channel]["hint"]
        answer = self.progress[channel]["answer"]
        i = hint.index("?")
        self.progress[channel]["hint"] = hint[:i] + answer[i] + hint[i+1:]

    def every_other_hint(self, channel):
        hint = self.progress[channel]["hint"]
        answer = self.progress[channel]["answer"]
        try:
            i = hint.index("??") + 1
            self.progress[channel]["hint"] = hint[:i] + answer[i] + (len(answer) - i - 1) * "?"
        except ValueError:  # ValueError thrown when no "??" in hint, so use default hint.
            self.default_hint(channel)

    def get_scrambled(self, channel):
        answer = self.progress[channel]["answer"]
        nspaces = answer.count(" ")
        answer = list(answer.replace(" ", ""))
        random.shuffle(answer)
        for _ in range(nspaces):
            while answer[(i := random.randint(1, len(answer)-2))] == " " or answer[i-1] == " ":
                pass
            answer.insert(i, " ")
        return "".join(answer)

    @property
    def default_progress(self):
        return {"answer": None, "hint": "", "future": None}

    def hints_left(self, channel):
        return channel in self.progress and "?" in self.progress[channel]["hint"]

    def in_progress(self, channel):
        return channel in self.progress and self.progress[channel]["answer"] is not None


class ScrambleManager:
    def __init__(self, scrambles):
        self.scrambles = scrambles

    def in_progress(self, identifier, channel):
        return self.scrambles[identifier].in_progress(channel)

    def hints_left(self, identifier, channel):
        return self.scrambles[identifier].hints_left(channel)

    def get_scramble(self, identifier, channel):
        self.scrambles[identifier].new_answer(channel)
        return self.scrambles[identifier].get_scrambled(channel)

    def get_hint(self, identifier, channel):
        return self.scrambles[identifier].update_hint(channel)

    def get_scramble_name(self, identifier):
        return self.scrambles[identifier].name

    def get_answer(self, identifier, channel):
        return self.scrambles[identifier].progress[channel]["answer"]

    def check_answer(self, identifier, channel, guess):
        scramble = self.scrambles[identifier]
        answer = scramble.progress[channel]["answer"]
        hint = scramble.progress[channel]["hint"]
        if (guess.lower() == answer.lower().strip() and not scramble.case_sensitive) or guess == answer.strip():
            return ScrambleRewardCalculator.calculate(scramble.reward_type, hint, scramble.difficulty_multiplier)

    def reset(self, identifier, channel, cancel=True):
        self.scrambles[identifier].reset(channel, cancel)

    def pass_future(self, identifier, channel, future):
        self.scrambles[identifier].progress[channel]["future"] = future


class AnimeCompareGame:
    def __init__(self, user, answers, score=0):
        self.id = None
        self.user = user
        self.answers = answers
        self.score = score
        self.finished = False

    @property
    def answer(self):
        return 1 if self.answers["anime1"][1] < self.answers["anime2"][1] else 2

    def get_question_string(self):
        return f"Which anime is more popular? {self.answers['anime1'][0]} or {self.answers['anime2'][0]}"

    def get_ranking_string(self):
        return f"Popularity ranking: {self.answers['anime1'][0]} - #{self.answers['anime1'][1]+1} | {self.answers['anime2'][0]} - #{self.answers['anime2'][1]+1}"


class AnimeCompare:
    def __init__(self, anime_list: list):
        self.current_games = []

    def generate_answer(self, anime_list, game=None) -> dict[str, tuple[str, int]]:
        anime1_i = random.randint(0, len(anime_list)-1)
        anime1 = anime_list.pop(anime1_i)
        anime2_i = random.randint(0, len(anime_list)-1)
        anime2 = anime_list.pop(anime2_i)
        anime_list.insert(anime1_i, anime1)
        answers = {
            "anime1": (anime1, anime1_i),
            "anime2": (anime2, anime2_i + (1 if anime2_i >= anime1_i else 0))
        }
        if game is None:
            return answers
        game.answers = answers

    def new_game(self, user, anime_list) -> AnimeCompareGame:
        game = AnimeCompareGame(user, self.generate_answer(anime_list))
        self.current_games.append(game)
        return game

    @staticmethod
    def check_guess(ctx, game):
        guess = ctx.message
        guess = "".join([char for char in guess if char.isascii()]).strip()  # Remove invis character from chatterino
        if not guess.isdigit() or int(guess) not in [1, 2]:
            return

        if int(guess) == game.answer:
            game.score += 1
            return True
        return False

    def get_game(self, user) -> AnimeCompareGame:
        for game in self.current_games:
            if game.user == user:
                return game

    def finish_game(self, game):
        game.finished = True
        index = -1
        for i, cgame in enumerate(self.current_games):
            if cgame.id == game.id:
                index = i
                break
        if index != -1:
            self.current_games.pop(index)

    def __contains__(self, user):
        return self.get_game(user) is not None


Cooldown = namedtuple("Cooldown", ["command_cd", "user_cd"])


class CommandPermission(IntEnum):
    NONE = 0
    ADMIN = 1


class DeniedUsageReason(IntFlag):
    NONE = 1 << 0
    COOLDOWN = 1 << 1
    PERMISSION = 1 << 2
    CHANNEL = 1 << 3
    BANNED = 1 << 4


class Command:
    permissions = {
        CommandPermission.NONE: lambda ctx: True,
        CommandPermission.ADMIN: lambda ctx: ctx.user_id in admins
    }

    def __init__(self, func, name, cooldown=Cooldown(3, 5), permission=CommandPermission.NONE, aliases=None,
                 banned=None, fargs=None, fkwargs=None):
        self.usage = {}
        self.name = name.lower()
        self.func = func
        self.permission = permission
        self.cooldown = cooldown
        self.aliases = list(map(str.lower, aliases)) if aliases is not None else []
        self.banned = banned
        self.fargs = fargs if fargs is not None else []
        self.fkwargs = fkwargs if fkwargs is not None else {}

    def print(self, out, *args, **kwargs):
        print(f"<{self.name}>: {str(out)}", *args, **kwargs)

    def check_permission(self, ctx):
        return DeniedUsageReason.NONE if self.permissions[self.permission](ctx) else DeniedUsageReason.PERMISSION

    def update_usage(self, ctx):
        if ctx.channel not in self.usage:
            self.usage[ctx.channel] = {"global": -self.cooldown.command_cd, "user": {ctx.user.username: -self.cooldown.user_cd}}
            return
        if ctx.user.username not in self.usage[ctx.channel]["user"]:
            self.usage[ctx.channel]["user"][ctx.user.username] = -self.cooldown.user_cd

    def check_cooldown(self, ctx):
        self.update_usage(ctx)
        return DeniedUsageReason.NONE if monotonic() - self.usage[ctx.channel]["global"] >= self.cooldown.command_cd and \
            monotonic() - self.usage[ctx.channel]["user"][ctx.user.username] >= self.cooldown.user_cd else DeniedUsageReason.COOLDOWN

    def check_banned(self, ctx):
        return DeniedUsageReason.NONE if self.banned is None or ctx.user.username not in self.banned else DeniedUsageReason.BANNED

    def check_can_use(self, ctx):
        return self.check_permission(ctx) | self.check_cooldown(ctx) | self.check_banned(ctx)

    def on_used(self, ctx):
        self.usage[ctx.channel]["global"] = monotonic()
        self.usage[ctx.channel]["user"][ctx.user.username] = monotonic()

    def __contains__(self, item):
        return item.lower() in self.aliases + [self.name]

    async def __call__(self, bot, ctx):
        can_use = self.check_can_use(ctx)
        if can_use == DeniedUsageReason.NONE:
            self.on_used(ctx)
            return await self.func(bot, ctx, *self.fargs, **self.fkwargs)
        if DeniedUsageReason.PERMISSION in can_use:
            return await bot.send_message(ctx.channel, f"@{ctx.user.username} You do not have permission to use this command.")
        elif DeniedUsageReason.BANNED in can_use:
            return await bot.send_message(ctx.channel, f"@{ctx.user.username} You are banned from using this command.")


class ChannelCommandInclusion(IntEnum):
    ALL = 0
    NONE = 1
    WHITELIST = 2
    BLACKLIST = 3


class ChannelConfig:
    def __init__(self, name, channel_id, command_inclusion=ChannelCommandInclusion.ALL, offlineonly=True, commands=None):
        self.name = name
        self.id = channel_id
        self.command_inclusion = command_inclusion
        self.offlineonly = offlineonly
        self.commands = commands if commands is not None else []

    def __contains__(self, item):
        return self.can_use_command(item)

    def can_use_command(self, command):
        if self.command_inclusion == ChannelCommandInclusion.ALL:
            return True
        if self.command_inclusion == ChannelCommandInclusion.NONE:
            return False
        if self.command_inclusion == ChannelCommandInclusion.WHITELIST:
            return command in self.commands
        if self.command_inclusion == ChannelCommandInclusion.BLACKLIST:
            return command not in self.commands


class CommandManager:
    def __init__(self):
        self.commands = []
        self.bot = None
        self.channels = {}

    def init(self, bot, channels):
        self.bot = bot
        self.load_channels(channels)

    def load_channels(self, channels):
        self.channels = {channel.name: channel for channel in channels}

    def command(self, *args, **kwargs):
        def decorator(func, *fargs, **fkwargs):
            func_args = {}
            if "fargs" not in kwargs:
                func_args.update({"fargs": fargs})
            if "fkwargs" not in kwargs:
                func_args.update({"fkwargs": fkwargs})
            self.commands.append(Command(func, *args, **kwargs, **func_args))
            return func
        return decorator

    async def __call__(self, command, ctx):
        if self.bot is None:
            raise Exception("CommandHandler must be initialized before being used to call commands.")
        if ctx.channel not in self.channels:
            return

        for c in self.commands:
            if command in c and c.name in self.channels[ctx.channel]:
                return await c(self.bot, ctx)


class TriviaHelper:
    trivia_info = {
        "hard": 100,
        "medium": 40,
        "easy": 20,
        "penalty": 0.25,
        "decrease": 0.5,
    }
    difficulty_emotes = {
        "easy": "EZ",
        "medium": "monkaS",
        "hard": "pepeMeltdown"
    }

    def __init__(self):
        self.guessed_answers = []
        self.future = None
        self.difficulty = None
        self.answer = None

    def generate_question(self, category=None):
        self.answer = "temp"

        params = {
            "amount": 1,
            "type": "multiple",
        }
        if category:
            params["category"] = category
        try:
            resp = requests.get("https://opentdb.com/api.php", params=params)
        except Exception as e:
            print(e)
            self.answer = None
            return
        if resp.status_code != 200:
            self.answer = None
            return

        try:
            results = resp.json()['results'][0]
        except IndexError:
            self.answer = None
            return
        answers = [results['correct_answer']] + results['incorrect_answers']
        random.shuffle(answers)
        self.answer = answers.index(results['correct_answer']) + 1
        self.difficulty = results['difficulty']

        answer_string = " ".join([html.unescape(f"[{i + 1}] {answers[i]} ") for i in range(len(answers))])
        return f"Difficulty: {self.difficulty} {self.difficulty_emotes[self.difficulty]} "\
               f"Category: {results['category']} veryPog "\
               f"Question: {html.unescape(results['question'])} monkaHmm "\
               f"Answers: {answer_string}"

    def check_guess(self, ctx, guess):
        if guess in self.guessed_answers:
            return
        self.guessed_answers.append(guess)
        if guess == self.answer:
            gain = self.trivia_info[self.difficulty] * (self.trivia_info['decrease'] ** (len(self.guessed_answers) - 1))
            self.reset()
            return f"@{ctx.user.display_name} ✅ You gained {gain} Becky Bucks 5Head Clap", gain
        else:
            loss = self.trivia_info[self.difficulty] * self.trivia_info['penalty']
            message = f"@{ctx.user.display_name} ❌ You lost {loss} Becky Bucks 3Head Clap"
            if len(self.guessed_answers) == 3:
                self.reset()
                message += " No one guessed correctly."
            return message, -loss

    def reset(self, cancel=True):
        self.answer = None
        self.difficulty = None
        self.guessed_answers = []
        if cancel:
            self.future.cancel()

    @property
    def is_in_progress(self):
        return self.answer is not None


def get_obj(data, key, cls, default=None):
    return default if (value:=data.get(key)) is None else cls(value)


class MWSenseCalledAlso:
    __slots__ = ("intro", "cats")

    def __init__(self, data):
        self.intro: str | None = data.get("intro")
        self.cats: list | None = data.get("cats")


class MWSenseBiographicalName:
    __slots__ = ("pname", "sname", "altname", "prs")

    def __init__(self, data):
        self.pname: str | None = data.get("pname")
        self.sname: str | None = data.get("sname")
        self.altname: str | None = data.get("altname")
        self.prs: list | None = data.get("prs")


class MWSenseDefinitionText:
    __slots__ = ("content",)

    def __init__(self, data):
        self.content: str = data


class MWSenseRunIn:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list = data


class MWSenseSupplementalInfo:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list = data


class MWSenseUsage:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list = data


class MWSenseVerbalIllustration:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list = data


SENSE_DEF_CONTENTS = (
    MWSenseDefinitionText |
    MWSenseBiographicalName |
    MWSenseCalledAlso |
    MWSenseRunIn |
    MWSenseSupplementalInfo |
    MWSenseUsage |
    MWSenseVerbalIllustration
)


class MWSenseDefinition:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list[SENSE_DEF_CONTENTS] = list(map(self.parse_content_item, data))

    @staticmethod
    def parse_content_item(data) -> SENSE_DEF_CONTENTS:
        return {
            "text": MWSenseDefinitionText,
            "bnw": MWSenseBiographicalName,
            "ca": MWSenseCalledAlso,
            "ri": MWSenseRunIn,
            "snote": MWSenseSupplementalInfo,
            "uns": MWSenseUsage,
            "vis": MWSenseVerbalIllustration
        }[data[0]](data[1])


class MWSense:
    __slots__ = (
        "etymology",
        "inflections",
        "labels",
        "pronunciations",
        "divided_sense",
        "grammatical_label",
        "status_labels",
        "sense_number",
        "variants",
        "definition",
        "sense_divider"
    )

    def __init__(self, data):
        self.etymology: list | None = data.get("et")
        self.inflections: list | None = data.get("ins")
        self.labels: list | None = data.get("lbs")
        self.pronunciations: list | None = data.get("prs")
        self.divided_sense: MWSense | None = get_obj(data, "sdsense", MWSense)
        self.grammatical_label: str | None = data.get("sgram")
        self.status_labels: list | None = data.get("sls")
        self.sense_number: str | None = data.get("sn")
        self.variants: list | None = data.get("vrs")
        self.definition: MWSenseDefinition | None = get_obj(data, "dt", MWSenseDefinition)
        self.sense_divider: str | None = data.get("sd")


class MWBindingSense:
    __slots__ = ("sense",)

    def __init__(self, data):
        self.sense: MWSense = MWSense(data["sense"])


class MWSequenceSense:
    __slots__ = ("senses",)

    def __init__(self, data):
        self.senses: list[MWSense | MWBindingSense | list[MWSense | MWBindingSense]] = list(map(self.parse_sense, data))

    @staticmethod
    def parse_sense(data) -> MWSense | MWBindingSense | list[MWSense | MWBindingSense]:

        return {
            "sense": MWSense,
            "sen": MWSense,
            "pseq": lambda data: [MWSense(elm[1]) if elm[0] == "sense" else MWBindingSense(elm[1]) for elm in data],
            "bs": MWBindingSense
        }[data[0]](data[1])


class MWDefinition:
    __slots__ = ("verb_divider", "sense_sequences")

    def __init__(self, data):
        self.verb_divider: str | None = data.get("vd")
        self.sense_sequences: list[MWSequenceSense] = list(map(MWSequenceSense, data.get("sseq", [])))


class MapGuessHelper:
    __slots__ = ("loop", "answers")

    def __init__(self, loop):
        self.loop = loop
        self.answers = {}

    def new(self, channel, beatmapset, timeout_callback, money, i=None) -> str:
        async def timeout():
            await asyncio.sleep(30)
            answer = self.complete(channel, cancel=False)
            await timeout_callback(answer)

        task = self.loop.create_task(timeout())

        top_diff = sorted(beatmapset.beatmaps, key=lambda b: b.difficulty_rating)[-1]
        attrs = [beatmapset.artist, beatmapset.title, top_diff.version, beatmapset.creator]

        mystery_attr = random.randint(0, 3) if i is None else i
        original = attrs[mystery_attr]
        attrs[mystery_attr] = " ".join(map(lambda s: "?"*len(s), original.split(" ")))

        self.answers[channel] = (original, task, money)
        return ("Fill in the blank (top difficulty): {} - {} [{}] (%.2f*) mapset by {}" % top_diff.difficulty_rating).format(*attrs)

    def check(self, channel, guess):
        if (item := self.answers.get(channel, None)) is not None and guess.lower() == item[0].lower():
            self.complete(channel)
            return item[2]
        return 0

    def complete(self, channel, cancel=True) -> str:
        item = self.answers.pop(channel)
        if cancel:
            item[1].cancel()
        return item[0]

    def in_progress(self, channel):
        return channel in self.answers


class BeatmapReader(br.BeatmapReader):
    __slots__ = ("lines",)

    def __init__(self, lines):
        super().__init__("")
        self.lines = lines

    def load_beatmap_data(self):
        data = {}
        current_section = None
        for line in self.lines:
            line = line[:-1]
            ascii_line = "".join(filter(lambda char: char.isascii(), line))
            if line.strip() == "" or line.startswith("//"):
                continue
            if current_section is None and ascii_line.startswith("osu file format"):
                data.update({"version": int(ascii_line[17:].strip())})
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                data.update({current_section: {} if current_section in self.key_value_sections else []})
                continue
            if current_section is None:
                continue
            if current_section in self.key_value_sections:
                kv = map(str.strip, line.split(":", 1))
                data[current_section].update({next(kv): next(kv)})
            else:
                data[current_section].append(line.strip())
        return data


LegacyStats = namedtuple("SimpleStats", ("n_geki", "n300", "n_katu", "n100", "n50", "misses"))


class BeatmapCalculator:
    __slots__ = ("beatmap", "info", "last_diff", "last_perf", "last_mods", "last_clock_rate", "last_passed", "beatmap_id")

    def __init__(self, beatmap: rosu.Beatmap, info: br.Beatmap, beatmap_id: int):
        self.beatmap: rosu.Beatmap = beatmap
        self.info: br.Beatmap = info
        self.last_diff: None | rosu.DifficultyAttributes = None
        self.last_perf: None | rosu.PerformanceAttributes = None
        self.last_mods: None | int = None
        self.last_clock_rate: None | float = None
        self.last_passed: None | bool = None
        self.beatmap_id = beatmap_id

    @classmethod
    async def from_beatmap_id(cls, beatmap_id: int) -> BeatmapCalculator | None:
        async with ClientSession() as session:
            async with session.get(f"https://osu.ppy.sh/osu/{beatmap_id}") as resp:
                try:
                    resp.raise_for_status()
                except Exception as e:
                    print("Failed to get osu beatmap", e)
                content = await resp.read()
                info = br.Beatmap(BeatmapReader(content.decode("utf-8").split("\n")))
                info.load()
                return cls(rosu.Beatmap(bytes=content), info, beatmap_id)

    @staticmethod
    def parse_stats(stats: osu.ScoreDataStatistics):
        values = (
            stats.perfect,
            stats.great,
            stats.good if stats.good is not None else stats.small_tick_miss,
            stats.ok if stats.ok is not None else stats.large_tick_hit,
            stats.meh,
            stats.miss,
        )
        return LegacyStats(*map(lambda h: h or 0, values))

    @staticmethod
    def hits_to_string(hits, ruleset_id) -> str:
        return "/".join(map(lambda i: str(hits[i]), {
            0: (1, 3, 4, 5),
            1: (1, 3, 5),
            2: (1, 4, 2, 5),
            3: (0, 1, 2, 3, 4, 5)
        }[ruleset_id]))

    @staticmethod
    def get_perf(stats: osu.ScoreDataStatistics, combo: int, mods: int, clock_rate: float, passed: bool = True) -> rosu.Performance:
        stats = BeatmapCalculator.parse_stats(stats)
        perf = rosu.Performance(
            n300=stats.n300,
            n100=stats.n100,
            n50=stats.n50,
            misses=stats.misses,
            n_geki=stats.n_geki,
            n_katu=stats.n_katu,
            combo=combo,
            mods=mods,
            clock_rate=clock_rate
        )
        if not passed:
            perf.set_passed_objects(sum(stats))
        return perf

    @staticmethod
    def get_score_settings(score: osu.SoloScore) -> tuple[int, float]:
        mods = sum(map(
            lambda m: osu.Mods[m.mod.name].value,
            filter(
                lambda m: not isinstance(m.mod, str) and m.mod.name in osu.Mods._member_names_,
                score.mods
            )
        ))
        clock_rate = 1.0
        for mod in score.mods:
            if mod.settings is not None and "speed_change" in mod.settings:
                return mods, mod.settings["speed_change"]
            if mod.mod == osu.Mod.DoubleTime or mod.mod == osu.Mod.Nightcore:
                return mods, 1.5
            if mod.mod == osu.Mod.HalfTime or mod.mod == osu.Mod.Daycore:
                return mods, 0.75

        return mods, clock_rate

    @staticmethod
    def calc_acc(stats, ruleset_id) -> float:
        if isinstance(stats, osu.ScoreDataStatistics):
            stats = BeatmapCalculator.parse_stats(stats)
        return {
            0: lambda s: (300 * s.n300 + 100 * s.n100 + 50 * s.n50) / (300 * (s.n300 + s.n100 + s.n50 + s.misses)),
            1: lambda s: (s.n300 + 0.5 * s.n_katu) / (s.n300 + s.n_katu + s.misses),
            2: lambda s: (s.n300 + s.n100 + s.n50) / (s.miss + s.n_katu + s.n300 + s.n100 + s.n50),
            3: lambda s: (300 * (s.n_geki + s.n300) + 200 * s.n_katu + 100 * s.n100 + 50 * s.n50) / (300 * (s.n_geki + s.n300 + s.n_katu + s.n100 + s.n50 + s.misses))
        }[ruleset_id](stats)

    def calculate_difficulty(self, mods: int, clock_rate: float | None = None) -> rosu.DifficultyAttributes:
        if clock_rate is None:
            clock_rate = 1.0
            if osu.Mods.DoubleTime.value & mods or osu.Mods.Nightcore.value & mods:
                clock_rate = 1.5
            elif osu.Mods.HalfTime.value & mods:
                clock_rate = 0.75
        self.last_diff = rosu.Difficulty(mods=mods, clock_rate=clock_rate).calculate(self.beatmap)
        self.last_mods = mods
        self.last_clock_rate = clock_rate
        return self.last_diff

    def calculate(self, score: osu.SoloScore) -> rosu.PerformanceAttributes:
        mods, clock_rate = self.get_score_settings(score)
        perf = self.get_perf(score.statistics, score.max_combo, mods, clock_rate, score.passed)
        self.last_perf = perf.calculate(
            self.beatmap if self.last_mods != mods or self.last_clock_rate != clock_rate or
            not score.passed or not self.last_passed else self.last_diff
        )
        self.last_diff = self.last_perf.difficulty
        self.last_mods = mods
        self.last_clock_rate = clock_rate
        self.last_passed = score.passed
        return self.last_perf

    def calculate_if_fc(self, score: osu.SoloScore) -> tuple[rosu.PerformanceAttributes, float]:
        mods, clock_rate = self.get_score_settings(score)

        diff = self.calculate_difficulty(mods, clock_rate) if self.last_diff is None or self.last_mods != mods \
            or self.last_clock_rate != clock_rate or not score.passed or not self.last_passed else self.last_diff

        stats = self.parse_stats(score.statistics)
        print(stats)
        stats = LegacyStats(
            stats.n_geki,
            stats.n300 + stats.misses if score.passed else
            stats.n300 + stats.misses + self.beatmap.n_objects - sum(stats),
            stats.n_katu,
            stats.n100,
            stats.n50,
            0,
        )
        print(stats)
        perf = rosu.Performance(
            n300=stats.n300,
            n100=stats.n100,
            n50=stats.n50,
            misses=stats.misses,
            n_geki=stats.n_geki,
            n_katu=stats.n_katu,
            combo=diff.max_combo,
            mods=mods,
            clock_rate=clock_rate
        )

        self.last_perf = perf.calculate(diff)
        self.last_diff = diff
        self.last_mods = mods
        self.last_clock_rate = clock_rate
        self.last_passed = score.passed

        return (
            self.last_perf,
            self.calc_acc(stats, score.ruleset_id)
        )

    def calculate_from_acc(self, acc: float) -> rosu.PerformanceAttributes:
        if self.last_diff is None:
            self.calculate_difficulty(0, 1.0)

        return rosu.Performance(
            accuracy=acc*100,
            mods=self.last_mods,
            clock_rate=self.last_clock_rate
        ).calculate(self.last_diff)


class TwitchAPIHelper:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id: str = client_id
        self.client_secret: str = client_secret
        self._token: str | None = None
        self._expires_at: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()
        
    async def get_token(self) -> str | None:
        if monotonic() >= self._expires_at - 5:
            await self._lock.acquire()
            await self._get_token()
            self._lock.release()

        return self._token
    
    async def _get_token(self):
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        data = await self.make_request(
            "post",
            "https://id.twitch.tv/oauth2/token",
            False,
            params=params
        )

        self._token = data["access_token"]
        self._expires_at = monotonic() + (data["expires_in"] / 1000)

    async def make_request(self, method, url, requires_auth: bool = True, return_on_error=None, **kwargs):
        if requires_auth:
            token = await self.get_token()
            if token is None:
                return return_on_error

            headers = {"Authorization": f"Bearer {token}", "Client-Id": self.client_id}
        else:
            headers = {}
        headers.update(kwargs.pop("headers", {}))

        try:
            async with ClientSession() as session:
                async with session.request(method, url, headers=headers, **kwargs) as resp:
                    data = await resp.json()
                    if "error" in data:
                        print(f"Request to {url} failed: {data['error']}")
                        return return_on_error

                    return data
        except client_exceptions.ClientError:
            return return_on_error

    async def get(self, endpoint, return_on_error=None, **kwargs):
        return await self.make_request(
            "get",
            "https://api.twitch.tv/"+endpoint,
            return_on_error=return_on_error,
            **kwargs
        )
