from ..static_data import StaticDataBot
from .emotes import EmoteRequester
from ...bot import BotMeta
from ...context import MessageContext, JoinContext

import random
import math
import logging
from enum import IntEnum
from typing import Callable

log = logging.getLogger(__name__)


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

    def __init__(
        self,
        name: str,
        answer_generator: Callable[[], str] | Callable[[str], str],
        difficulty_multiplier: float = 1.0,
        hint_type: ScrambleHintType = ScrambleHintType.DEFAULT,
        case_sensitive: bool = False,
        reward_type: ScrambleRewardType = ScrambleRewardType.LINEAR
    ):
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
            log.info(f"Cancelling future for {self.name} scramble")
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


class ScrambleBot(StaticDataBot, metaclass=BotMeta):
    __slots__ = ("emote_requester", "emotes", "scrambles", "scramble_manager")

    command_manager = StaticDataBot.command_manager

    def __init__(self):
        self.emote_requester = EmoteRequester(self.twitch_client)
        self.emotes = {}

        self.scrambles = {
            "word": Scramble("word", lambda: random.choice(self.word_list), 1),
            "osu": Scramble("player name", lambda: random.choice(self.top_players), 0.8),
            "map": Scramble("map name", lambda: random.choice(self.top_maps), 1.3),
            "genshin": Scramble("genshin weap/char", lambda: random.choice(self.genshin), 0.7),
            "emote": Scramble("emote", lambda channel: random.choice(self.emotes[channel]), 0.7,
                              ScrambleHintType.EVERY_OTHER, True, ScrambleRewardType.LOGARITHM),
            "anime": Scramble("anime", lambda: random.choice(self.anime[:250]), 1.1),
            "al": Scramble("azurlane ship", lambda: random.choice(self.azur_lane), 0.9),
        }
        self.scramble_manager = ScrambleManager(self.scrambles)

    async def on_message(self, ctx: MessageContext):
        for scramble_type, scramble in self.scrambles.items():
            if scramble.in_progress(ctx.channel):
                await self.on_scramble(ctx, scramble_type)

    async def on_join(self, ctx: JoinContext):
        channel = next((channel for channel in self.channels if channel.user.username == ctx.channel), None)
        self.emotes[ctx.channel] = await self.emote_requester.get_channel_emotes(
            channel.id if channel is not None else ctx.channel
        )

    @command_manager.command("scramble", "unscramble the word", scramble_type="word")
    @command_manager.command("scramble_osu", "unscramble the osu player", scramble_type="osu")
    @command_manager.command("scramble_map", "unscramble the osu map title", scramble_type="map")
    @command_manager.command("scramble_emote", "unscramble the emote", scramble_type="emote")
    @command_manager.command("scramble_genshin", "unscramble the genshin character/weapon", scramble_type="genshin")
    @command_manager.command("scramble_anime", "unscramble the anime title (english)", scramble_type="anime")
    @command_manager.command("scramble_al", "unscramble the azur lane ship", scramble_type="al")
    async def scramble(self, ctx, scramble_type):
        if self.scramble_manager.in_progress(scramble_type, ctx.channel):
            return
        if scramble_type == "emote" and len(self.emotes[ctx.channel]) < 20:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Must have at least 20 emotes "
                                                        "in this channel to use the emote scramble.")

        scrambled_word = self.scramble_manager.get_scramble(scramble_type, ctx.channel)
        future = self.call_later(120, self.on_scramble_finish, ctx.channel, scramble_type)
        self.scramble_manager.pass_future(scramble_type, ctx.channel, future)

        await self.send_message(ctx.channel, f"Unscramble this "
                                             f"{self.scramble_manager.get_scramble_name(scramble_type)}: "
                                             f"{scrambled_word.lower()}")

    async def on_scramble(self, ctx, scramble_type):
        money = self.scramble_manager.check_answer(scramble_type, ctx.channel, ctx.message)
        if money is None:
            return
        answer = self.scramble_manager.get_answer(scramble_type, ctx.channel)
        name = self.scramble_manager.get_scramble_name(scramble_type)
        self.scramble_manager.reset(scramble_type, ctx.channel)
        await self.send_message(ctx.channel,
                                f"@{ctx.user.display_name} You got it right! "
                                f"{answer} was the "
                                f"{name}. Drake "
                                f"You've won {money} Becky Bucks!")
        await self.db.add_money(ctx.user_id, ctx.sending_user, money)

    @command_manager.command("hint", "hint for word scramble", scramble_type="word")
    @command_manager.command("hint_osu", "hint for osu scramble", scramble_type="osu")
    @command_manager.command("hint_map", "hint for osu map scramble", scramble_type="map")
    @command_manager.command("hint_emote", "hint for emote scramble", scramble_type="emote")
    @command_manager.command("hint_genshin", "hint for genshin scramble", scramble_type="genshin")
    @command_manager.command("hint_anime", "hint for anime scramble", scramble_type="anime")
    @command_manager.command("hint_al", "hint for azur lane scramble", scramble_type="al")
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

    @command_manager.command(
        "scramble_multipliers",
        "posts a message about scramble multipliers",
        aliases=["scramblemultipliers", "scramble_multiplier", "scramblemultiplier"]
    )
    async def scramble_difficulties(self, ctx):
        await self.send_message(ctx.channel,
                                f"@{ctx.user.display_name} Difficulty multiplier for each scramble: "
                                "%s" % ', '.join(
                                    ['%s-%s' % (identifier, scramble.difficulty_multiplier)
                                     for identifier, scramble in self.scrambles.items()])
                                )

    @command_manager.command(
        "scramble_calc",
        "posts a message about scramble calculation",
        aliases=["scramblecalc"]
    )
    async def scramble_calc(self, ctx):
        await self.send_message(ctx.channel,
                                f"@{ctx.user.display_name} Scramble payout is calculated by picking a random number 5-10, "
                                f"multiplying that by the length of the word (excluding spaces), multiplying "
                                f"that by hint reduction, and multiplying that by the scramble difficulty "
                                f"multiplier for that specific scramble. To see the difficulty multipliers, "
                                f"do !scramble_multiplier. Hint reduction is the length of the word minus the "
                                f"amount of hints used divided by the length of the word.")
