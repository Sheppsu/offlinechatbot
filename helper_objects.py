import json
import random
from time import perf_counter
from enum import IntEnum, IntFlag
from collections import namedtuple
from constants import admins


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
            if self.started:
                self.party[user].lives = 0
            else:
                del self.party[user]

    def on_in_progress(self):
        self.in_progress = True

    def on_start(self):
        self.turn_order = list(self.party.keys())
        random.shuffle(self.turn_order)
        self.timer = self.bomb_settings['timer']
        self.bomb_start_time = perf_counter()
        self.started = True

    def on_word_used(self, message):
        message = message.lower()
        self.timer -= max((0, perf_counter() - self.bomb_start_time - self.bomb_settings['minimum_time']))
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
        self.bomb_start_time = perf_counter()

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
        return len(self.party) * 100

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


class Scramble:
    banned_words = [
        # Was originally used to stop this word from being posted for scramble,
        # but since there's a new list with non-tos words it doesn't really do anything
        "kike"
    ]

    def __init__(self, name, answer_generator, difficulty_multiplier=1, hint_type=ScrambleHintType.DEFAULT, case_sensitive=False):
        self.name = name
        self.difficulty_multiplier = difficulty_multiplier
        self.hint_type = hint_type
        self.case_sensitive = case_sensitive

        self.progress = {}

        self.generate_answer = answer_generator

    def reset(self, channel, cancel=True):
        future = self.progress[channel]["future"]
        self.progress[channel] = self.default_progress
        if cancel and future is not None and not future.cancelled() and not future.done():
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
        chars = list(self.progress[channel]["answer"])
        random.shuffle(chars)
        return "".join(chars)

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
            return round(
                random.randint(5, 10) *
                len(answer.replace(" ", "")) *
                hint.count("?")/len(answer) *
                scramble.difficulty_multiplier
            )

    def reset(self, identifier, channel, cancel=True):
        self.scrambles[identifier].reset(channel, cancel)

    def pass_future(self, identifier, channel, future):
        self.scrambles[identifier].progress[channel]["future"] = future


class Trivia:
    def __init__(self):
        pass


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
        return f"Popularity ranking: {self.answers['anime1'][0]} - #{self.answers['anime1'][1]} | {self.answers['anime2'][0]} - #{self.answers['anime2'][1]}"


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
        CommandPermission.ADMIN: lambda ctx: ctx.user.username in admins
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
        return DeniedUsageReason.NONE if perf_counter() - self.usage[ctx.channel]["global"] >= self.cooldown.command_cd and \
            perf_counter() - self.usage[ctx.channel]["user"][ctx.user.username] >= self.cooldown.user_cd else DeniedUsageReason.COOLDOWN

    def check_banned(self, ctx):
        return DeniedUsageReason.NONE if self.banned is None or ctx.user.username not in self.banned else DeniedUsageReason.BANNED

    def check_can_use(self, ctx):
        return self.check_permission(ctx) | self.check_cooldown(ctx) | self.check_banned(ctx)

    def on_used(self, ctx):
        self.usage[ctx.channel]["global"] = perf_counter()
        self.usage[ctx.channel]["user"][ctx.user.username] = perf_counter()

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
        if ctx.channel not in self.channels or command not in self.channels[ctx.channel]:
            return

        for c in self.commands:
            if command in c:
                return await c(self.bot, ctx)
