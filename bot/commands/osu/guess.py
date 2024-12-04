from ...context import MessageContext
from ..base import CommandArg
from ...bot import BotMeta
from .client import OsuClientBot

import asyncio
import random
from osu import BeatmapsetSearchFilter, BeatmapsetSearchSort, GameModeInt


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


class OsuGuessBot(OsuClientBot, metaclass=BotMeta):
    __slots__ = ("osu_guess_helper",)

    command_manager = OsuClientBot.command_manager

    def __init__(self):
        self.osu_guess_helper = MapGuessHelper(self.loop)

    async def on_message(self, ctx: MessageContext):
        if (money := self.osu_guess_helper.check(ctx.channel, ctx.message)) != 0:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Correct! You get {money} Becky Bucks."
            )
            await self.db.add_money(ctx.user_id, ctx.sending_user, money)
            return

    @command_manager.command(
        "osuguess",
        "guess the missing component of the osu map",
        [
            CommandArg(
                "category",
                "component that will be missing from the beatmap: artist, title, difficulty, or mapper",
                is_optional=True
            ),
            CommandArg(
                "difficulty",
                "easy, medium, or hard",
                is_optional=True,
                flag="d"
            )
        ]
    )
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
            i // 50 + 1
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
