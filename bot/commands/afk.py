from .base import CommandBot, CommandArg
from ..context import MessageContext
from ..database import UserAfk
from ..util import format_date
from ..bot import BotMeta

from time import time
import asyncio


class AFKBot(CommandBot, metaclass=BotMeta):
    __slots__ = ("afks", "_lock")

    command_manager = CommandBot.command_manager

    def __init__(self):
        self.afks: list[UserAfk] = None  # type: ignore
        self._lock: asyncio.Lock = asyncio.Lock()

    async def on_message(self, ctx: MessageContext):
        if not self.can_respond(ctx):
            return

        await self._lock.acquire()
        await self.on_afk(ctx)
        self._lock.release()

    async def on_setup(self, ctx):
        self.afks = await self.db.get_afks()

    @command_manager.command(
        "afk",
        "Set an AFK (away from keyboard) status. When pinged, the bot will notify the user that you're AFK. "
        "When sending another message (after at least 1 minute), the AFK status is automatically removed. "
        "To prevent this, you can change the 'auto_remove_afk' setting with the !toggle command. "
        "In that case, AFK status can be manually removed with the !removeafk command.",
        [
            CommandArg("message", is_optional=True)
        ]
    )
    async def afk(self, ctx: MessageContext):
        await self._lock.acquire()

        args = ctx.get_args()
        message = " ".join(args)

        self.afks.append(
            await self.db.set_afk(ctx.user_id, ctx.sending_user, message)
        )

        self._lock.release()

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Your afk has been set.")

    @command_manager.command(
        "removeafk",
        "Manually remove afk status. Only used if the auto_remove_afk setting is off.",
        aliases=["rafk", "afkremove", "afkr", "unafk"]
    )
    async def afk_remove(self, ctx):
        await self._lock.acquire()

        for afk in self.afks:
            if afk.user.id == ctx.user_id:
                await self.remove_user_afk(ctx, afk)
                return

        self._lock.release()

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You are not afk")

    async def on_afk(self, ctx):
        pings = set([
            word.replace("@", "")
            for word in ctx.message.lower().replace(",", "").replace(".", "").replace("-", "").split()
            if word.startswith("@")
        ])
        for ping in pings:
            for afk in self.afks:
                if afk.user.username == ping:
                    await self.send_message(
                        ctx.channel,
                        f"@{ctx.user.display_name} {ping} is afk ({format_date(afk.timestamp)} ago): {afk.msg}"
                    )
                    break

        afk = next((afk for afk in self.afks if afk.user.id == ctx.user_id), None)
        if afk is None:
            return

        user = await self.db.get_user(ctx.user_id, ctx.sending_user)
        if not user.auto_remove_afk:
            return

        if time() - afk.timestamp > 60:
            await self.remove_user_afk(ctx, afk)

    async def remove_user_afk(self, ctx: MessageContext, afk: UserAfk):
        self.afks.remove(afk)
        await self.db.remove_afk(afk.id)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Your afk has been removed. "
            f"(Afk for {format_date(afk.timestamp)})"
        )
