from ..context import MessageContext, JoinContext, UserStateContext, ServerMessageContext
from ..bot import BaseBot, BotMeta
from ..database import UserChannel, User, ChannelCommand, Command

from collections import namedtuple, defaultdict
from typing import Callable, Awaitable
from time import monotonic
import asyncio
import random


Cooldown = namedtuple("Cooldown", ["command_cd", "user_cd"])


class CommandArg:
    __slots__ = ("name", "description", "is_optional", "flag")

    def __init__(self, name: str, description: str | None = None, is_optional: bool = False, flag: str | None = None):
        self.name: str = name
        self.description: str | None = description
        self.is_optional: bool = is_optional
        self.flag: str | None = flag

    def json(self):
        return {
            "n": self.name,
            "d": self.description,
            "o": self.is_optional,
            "f": self.flag,
        }


class CallableCommand:
    __slots__ = ("function", "name", "description", "args", "aliases", "cooldown", "kwargs", "user_usage", "cmd_usage")

    def __init__(
        self,
        function: Callable[[BaseBot, MessageContext, ...], Awaitable],
        name: str,
        description: str,
        args: list[CommandArg],
        aliases: list[str],
        cooldown: Cooldown,
        **kwargs
    ):
        self.function = function
        self.name: str = name
        self.description: str = description
        self.args: list[CommandArg] = args
        self.aliases: list[str] = aliases
        self.cooldown: Cooldown = cooldown
        self.kwargs: dict = kwargs

        self.user_usage: defaultdict[int, dict[int, float]] = defaultdict(dict)
        self.cmd_usage: dict[int, float] = {}

    def update_usage(self):
        now = monotonic()
        self.user_usage = {
            ch: {
                user: ts
                for user, ts in usage.items()
                if now - ts >= self.cooldown.user_cd
            } for ch, usage in self.user_usage.items()
        }
        self.cmd_usage = {
            ch: ts
            for ch, ts in self.cmd_usage.items()
            if now - ts >= self.cooldown.command_cd
        }

    def can_use(self, ctx: MessageContext) -> bool:
        now = monotonic()
        cmd_cd = self.cooldown.command_cd
        user_cd = self.cooldown.user_cd

        return (
            now - self.cmd_usage.get(ctx.room_id, now - cmd_cd - 1) >= cmd_cd and (
                (room_usage := self.user_usage.get(ctx.room_id)) is None or
                now - room_usage.get(ctx.user_id, now - user_cd - 1) >= user_cd
            )
        )

    def __call__(self, bot: BaseBot, ctx: MessageContext) -> Awaitable:
        self.user_usage[ctx.room_id][ctx.user_id] = (now := monotonic())
        self.cmd_usage[ctx.room_id] = now

        return self.function(bot, ctx, **self.kwargs)


class CommandManager:
    __slots__ = ("commands",)

    def __init__(self):
        self.commands: list[CallableCommand] = []

    def command(
        self,
        name: str,
        description: str,
        args: list[CommandArg] = None,
        aliases: list[str] = None,
        cooldown: Cooldown = None,
        **kwargs
    ):
        if args is None:
            args = []
        if aliases is None:
            aliases = []
        if cooldown is None:
            cooldown = Cooldown(3, 5)

        def decorator(func):
            self.commands.append(CallableCommand(func, name, description, args, aliases, cooldown, **kwargs))

            return func

        return decorator

    def get_command(self, name: str) -> CallableCommand | None:
        return next((cmd for cmd in self.commands if cmd.name == name or name in cmd.aliases), None)


class CommandBot(BaseBot, metaclass=BotMeta):
    __slots__ = ("channels", "offline_channels", "last_checked_live")

    command_manager = CommandManager()

    def __init__(self):
        self.channels: list[UserChannel] = None
        self.offline_channels: dict[str, bool] = None

        self.last_checked_live: float = monotonic()

    async def on_update(self, ctx):
        if monotonic() - self.last_checked_live >= 10:
            self.last_checked_live = monotonic()
            await self.update_stream_statuses()

    async def on_setup(self, ctx):
        await self.db.sync_commands(self.command_manager.commands)

        if self.IS_DEBUG:
            self.channels = [ch for ch in await self.db.get_channels() if ch.is_enabled and ch.id == 19]
        else:
            self.channels = [ch for ch in await self.db.get_channels() if ch.is_enabled]

        self.offline_channels = {
            channel.user.username: False
            for channel in self.channels
            if channel.is_offline_only
        }
        await self.update_stream_statuses()

    async def on_connected(self, ctx):
        await self.register_cap("tags")
        await self.register_cap("commands")
        for channel in self.channels:
            await self.join(channel.user.username)

    async def on_user_state(self, ctx: UserStateContext):
        if ctx.username == self.IRC_USERNAME:
            self.own_state = ctx

    async def on_join(self, ctx: JoinContext):
        # probably reconnecting to the channel
        if ctx.channel in self.message_locks:
            return

        self.message_locks[ctx.channel] = asyncio.Lock()
        self.last_message[ctx.channel] = ""

    async def on_reconnect(self, ctx):
        self.running = False

    async def on_message(self, ctx: MessageContext):
        if not self.can_respond(ctx):
            return

        cmd_msg = "".join((
            char
            for char in (" ".join(ctx.message.split()[1:]) if ctx.reply else ctx.message).strip()
            if char.isascii()
        ))

        if cmd_msg.startswith("!"):
            callable_cmd = self.command_manager.get_command(cmd_msg.split()[0].lower().replace("!", ""))
            if callable_cmd is None or not callable_cmd.can_use(ctx):
                return

            channel = next((channel for channel in self.channels if channel.user.id == ctx.room_id))
            cmd = next((ch_cmd for ch_cmd in channel.commands if ch_cmd.command.name == callable_cmd.name))
            if not cmd.is_enabled:
                return

            self.loop.create_task(callable_cmd(self.manager.get_bot_for(callable_cmd.function), ctx))

    async def send_message(self, channel, message):
        if not self.can_send_in_channel(channel):
            return

        return await super().send_message(channel, message)

    # Util

    def can_respond(self, ctx: MessageContext) -> bool:
        return self.can_send_in_channel(ctx.channel) and ctx.sending_user != self.IRC_USERNAME

    def can_send_in_channel(self, channel: str) -> bool:
        return self.offline_channels.get(channel, True)

    async def update_stream_statuses(self):
        # TODO: account for limit of 100
        channels = [
            channel.user.id
            for channel in self.channels
            if channel.is_offline_only
        ]
        params = {"user_id": channels}

        data = await self.twitch_client.get("helix/streams", params=params)
        if data is None:
            for channel in self.offline_channels.keys():
                self.offline_channels[channel] = False

            return

        data = data["data"]
        online_streams = [int(user["user_id"]) for user in data]

        for channel in self.channels:
            if not channel.is_offline_only:
                continue

            self.offline_channels[channel.user.username] = channel.id not in online_streams

    def process_value_arg(self, flag, args, default=None):
        lower_args = list(map(str.lower, args))
        if flag in lower_args:
            index = lower_args.index(flag)
            args.pop(index)
            if len(args) == 0:
                return
            value = args.pop(index).strip()
            return value
        return default

    def process_arg(self, flag, args):
        lower_args = list(map(str.lower, args))
        if flag in lower_args:
            args.pop(lower_args.index(flag))
            return True
        return False

    async def process_index_arg(self, ctx, args, rng=range(1, 101)):
        arg = self.process_value_arg("-i", args, -1)
        if arg == -1:
            return -1
        if arg is None:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must specify an index with the -i argument. "
                f"Specify a number between {rng[0]} and {rng[-1]}"
            )
            return
        if arg.lower() == "random":
            return random.choice(rng)-1
        if type(arg) != int and (not arg.isdigit() or int(arg) not in rng):
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must specify a number between "
                f"{rng[0]} and {rng[-1]} for the -i argument."
            )
            return
        return int(arg)-1
