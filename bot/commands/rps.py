from .base import CommandBot, Cooldown, CommandArg
from ..bot import BotMeta

import random


class RPSBot(CommandBot, metaclass=BotMeta):
    command_manager = CommandBot.command_manager

    @command_manager.command(
        "rps",
        "Play rock paper scissors and win or lose becky bucks. ",
        [
            CommandArg("play", "either rock, paper, or scissors (or the first letter)")
        ],
        cooldown=Cooldown(2, 4)
    )
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
            return await self.send_message(ctx.channel,
                                           f"@{ctx.user.display_name} I also chose {abbr[com_choice]}! bruh")
        if win[com_choice] == choice:
            await self.db.add_money(ctx.user_id, ctx.sending_user, -10)
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} LETSGO I won, {abbr[com_choice]} beats {abbr[choice]}. "
                "You lose 10 Becky Bucks!"
            )
        await self.db.add_money(ctx.user_id, ctx.sending_user, 10)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} IMDONEMAN I lost, {abbr[choice]} beats {abbr[com_choice]}. "
            "You win 10 Becky Bucks!"
        )