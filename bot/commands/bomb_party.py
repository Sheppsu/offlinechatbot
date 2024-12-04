# TODO: this entire file needs a makeover

from .base import Cooldown, CommandArg
from .static_data import StaticDataBot
from ..context import MessageContext
from ..bot import BotMeta

import random
import json
from time import monotonic


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
        self.timer = self.bomb_settings['timer']
        self.bomb_start_time = 0
        player = self.current_player
        player.lives -= 1
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
        players_left = [player for player in self.party.values() if player.lives != 0]
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


class BombPartyBot(StaticDataBot, metaclass=BotMeta):
    __slots__ = ("bomb_party_helper", "bomb_party_future", "exploding")

    command_manager = StaticDataBot.command_manager

    def __init__(self):
        self.bomb_party_helper = BombParty()
        self.bomb_party_future = None
        self.exploding = False

    async def on_message(self, ctx: MessageContext):
        if self.bomb_party_helper.started:
            await self.on_bomb_party(ctx)

    @command_manager.command(
        "bombparty",
        "Start a bomb party game. In bomb party, players take turns getting a short string "
        "of letters and saying a word with those letters (in matching order). Words cannot "
        "be repeated and if a player fails to give a word within the time limit, they lose "
        "a life. Upon losing all lives, they're out of the game. The time limit reduces over "
        "time until a player explodes and it resets. Settings can be changed via the !settings "
        "command.",
        aliases=["bomb_party"]
    )
    async def bomb_party(self, ctx):
        if self.bomb_party_helper.in_progress:
            return
        self.bomb_party_helper.add_player(ctx.user.username)
        self.bomb_party_helper.on_in_progress()

        await self.send_message(ctx.channel,
                                f"{ctx.user.username} has started a Bomb Party game! Anyone else who wants to play should type !join. When enough players have joined, the host should type !start to start the game, otherwise the game will automatically start or close after 2 minutes.")
        self.bomb_party_future = self.call_later(120, self.close_or_start_game, ctx.channel)

    async def close_or_start_game(self, channel):
        if not self.bomb_party_helper.can_start:
            self.bomb_party_helper.on_close()
            return await self.send_message(channel,
                                           "The bomb party game has closed since there is only one player in the party.")
        await self.start_bomb_party(MessageContext("", channel), True)

    @command_manager.command(
        "start",
        "Start the bomb party game. Needs at least 2 players to start. The game can be opened with !bombparty."
    )
    async def start_bomb_party(self, ctx, auto=False):
        if not auto and (not self.bomb_party_helper.in_progress or
                         self.bomb_party_helper.started or
                         ctx.user.username != self.bomb_party_helper.host):
            return
        if not self.bomb_party_helper.can_start:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You need at least 2 players to start the bomb party game."
            )
        if not auto:
            self.bomb_party_future.cancel()

        self.bomb_party_helper.on_start()
        self.bomb_party_helper.set_letters()

        await self.send_message(ctx.channel,
                                f"@{self.bomb_party_helper.current_player} You're up first! Your string of letters is {self.bomb_party_helper.current_letters}")
        self.bomb_party_future = self.call_later(self.bomb_party_helper.starting_time, self.bomb_party_timer,
                                                 ctx.channel)

    @command_manager.command(
        "join",
        "Join a currently open bomb party game. A game can be opened with !bombparty. You can leave with !leave.",
        cooldown=Cooldown(0, 3)
    )
    async def join_bomb_party(self, ctx):
        if not self.bomb_party_helper.in_progress or self.bomb_party_helper.started:
            return
        if ctx.user.username in self.bomb_party_helper.party:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} You have already joined the game")

        self.bomb_party_helper.add_player(ctx.user.username)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You have joined the game of bomb party!")

    @command_manager.command(
        "leave",
        "Leave a currently open bomb party game. A game can be opened with !bombparty. You can join with !join.",
        cooldown=Cooldown(0, 3)
    )
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

    @command_manager.command(
        "settings",
        "Change the settings of a bomb party game.",
        [
            CommandArg("setting", f"Valid settings are {", ".join(BombParty.valid_bomb_settings.keys())}"),
            CommandArg(
                "value",
                "Value to set the setting to. Values for difficulty are: easy, medium, hard, nightmare, impossible"
            )
        ],
        cooldown=Cooldown(0, 0)
    )
    async def change_bomb_settings(self, ctx):
        if not self.bomb_party_helper.in_progress or \
                self.bomb_party_helper.started or \
                self.bomb_party_helper.host != ctx.user.username:
            return
        args = ctx.get_args("ascii")
        if len(args) < 2:
            return await self.send_message(ctx.channel,
                                           f"@{ctx.user.display_name} You must provide a setting name and the value: "
                                           f"!settings <setting> <value>. Valid settings: "
                                           f"{self.bomb_party_helper.valid_settings_string}")
        setting = args[0]
        value = args[1]
        return_msg = self.bomb_party_helper.set_setting(setting, value)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} {return_msg}")

    @command_manager.command(
        "players",
        "List the players currently in bomb party."
    )
    async def player_list(self, ctx):
        if not self.bomb_party_helper.in_progress:
            return
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Current players playing bomb party: "
            f"{', '.join(self.bomb_party_helper.player_list)}"
        )

    async def bomb_party_timer(self, channel):
        self.exploding = True
        msg = self.bomb_party_helper.on_explode()
        await self.send_message(channel, msg)

        if await self.check_win(channel):
            return

        self.exploding = False

        await self.next_player(channel)

    async def next_player(self, channel):
        self.bomb_party_helper.next_player()
        self.bomb_party_helper.set_letters()
        player = self.bomb_party_helper.current_player
        await self.send_message(channel,
                                f"@{player} Your string of letters is {self.bomb_party_helper.current_letters} - "
                                f"You have {round(self.bomb_party_helper.seconds_left)} seconds.")
        self.bomb_party_future = self.call_later(self.bomb_party_helper.seconds_left, self.bomb_party_timer,
                                                 channel)

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
        user = await self.db.get_user_if_exists(winner)
        # TODO: I need to fix this later
        if user is not None:
            await self.db.add_money(user.id, user.username, money)
        self.close_bomb_party(False)
        await self.send_message(
            channel,
            f"@{winner} Congratulations on winning the bomb party game! You've won {money} Becky Bucks!"
        )
        return True

    def close_bomb_party(self, cancel=True):
        if cancel and not self.bomb_party_future.done():
            self.bomb_party_future.cancel()
        self.bomb_party_future = None
        self.bomb_party_helper.on_close()
