from .base import Cooldown
from .static_data import StaticDataBot
from ..context import MessageContext
from ..bot import BotMeta

import random


class PullBot(StaticDataBot, metaclass=BotMeta):
    command_manager = StaticDataBot.command_manager

    @command_manager.command(
        "pull",
        "Simulate a genshin pull. Check your pity with !pity.",
        cooldown=Cooldown(1, 2),
    )
    async def pull(self, ctx: MessageContext):
        pity = await self.db.get_pity(ctx.user_id, ctx.sending_user)

        pity = (pity[0] + 1, pity[1] + 1)
        if pity[0] == 10 and pity[1] != 90:
            pull = 4
        elif pity[1] == 90:
            pull = 5
        else:
            num = random.randint(1, 1000)
            pull = 3
            if num <= (300 - 20 * (pity[1] - 76) if pity[1] >= 76 else 6):
                pull = 5
            elif num <= 57:
                pull = 4

        end_msg = {3: ". 😔", 4: "! Pog", 5: "! PogYou"}[pull]
        stars = "\u2B50\u2B50\u2B50" if pull == 3 else '🌟' * pull
        pulls_in = f" Rolls in: {pity[pull - 4]}" if pity != 3 else ""
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} You pulled {random.choice(self.pull_options[str(pull)])} " +
            end_msg + stars + pulls_in
        )

        if pull == 5:
            pity = (0, 0)
        elif pull == 4:
            pity = (0, pity[1])

        await self.db.set_pity(ctx.user_id, pity[0], pity[1])

    @command_manager.command(
        "pity",
        "Check your pity for !pull.",
    )
    async def pity(self, ctx):
        pity = await self.db.get_pity(ctx.user_id, ctx.sending_user)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} 4* pity in {10 - pity[0]} rolls; 5* pity in {90 - pity[1]} rolls."
        )
