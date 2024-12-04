from .base import CommandBot, Cooldown, CommandArg
from ..bot import BotMeta

import random


class GuessBot(CommandBot, metaclass=BotMeta):
    __slots__ = ("number",)

    command_manager = CommandBot.command_manager

    def __init__(self):
        self.number = random.randint(1, 1000)

    @command_manager.command(
        "guess",
        "Guess a number between 1 and 1000 and receive feedback about whether it's higher or lower until you get it.",
        [
            CommandArg("number", "Number between 1 and 1000")
        ],
        cooldown=Cooldown(2, 3)
    )
    async def guess(self, ctx):
        args = ctx.get_args()
        if len(args) < 1:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You must provide a number 1-1000 to guess with"
            )

        if not args[0].isdigit():
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} That's not a valid number OuttaPocket Tssk"
            )

        guess = int(args[0])

        if self.number == guess:
            await self.send_message(ctx.channel, f"@{ctx.user.display_name} You got it PogYou")
            self.number = random.randint(1, 1000)
        else:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} It's not {guess}. Try guessing " +
                ("higher" if guess < self.number else "lower") +
                ". veryPog"
            )
