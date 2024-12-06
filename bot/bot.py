from .database import Database
from .context import *
from .util import *
from .twitch_api import TwitchAPIHelper
from .server import MessageServer

import websockets
import os
import asyncio
import sys


log = logging.getLogger(__name__)


class BaseBot:
    __slots__ = (
        "db",
        "ws",
        "running",
        "loop",
        "last_message",
        "message_locks",
        "own_state",
        "manager",
        "twitch_client"
    )

    TWITCH_CLIENT_ID = os.getenv("CLIENT_ID")
    TWITCH_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    IRC_USERNAME = os.getenv("IRC_USERNAME")
    IRC_OAUTH = os.getenv("IRC_OAUTH")
    IRC_URI = "ws://irc-ws.chat.twitch.tv:80"

    if IRC_USERNAME is None or IRC_OAUTH is None:
        raise RuntimeError("irc username or password could not be loaded from environment variables")

    IS_DEBUG = "--debug" in sys.argv

    dependencies = []

    def __init__(self, loop: asyncio.AbstractEventLoop, manager: "BotManager"):
        self.db = Database()

        self.ws = None
        self.running: asyncio.Event = asyncio.Event()
        self.loop: asyncio.AbstractEventLoop = loop
        self.last_message = {}
        self.message_locks = {}
        self.own_state = None
        self.manager = manager

        self.twitch_client: TwitchAPIHelper = TwitchAPIHelper(os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET"))

    # Fundamental

    async def run(self) -> bool:
        async with websockets.connect(self.IRC_URI) as ws:
            self.ws = ws

            try:
                await self.connect()
                self.loop.create_task(self.run_update())
                await self.run_receiver()

            except KeyboardInterrupt:
                return False

            except Exception as exc:
                log.exception(exc)

        return True

    async def run_update(self):
        while self.running.is_set():
            await asyncio.sleep(1)
            await self.manager.queue_ctx(UnknownContext(None, ContextType.UPDATE))

    async def run_receiver(self):
        while self.running.is_set():
            data = await self.ws.recv()

            if data.startswith("PING"):
                await self.ws.send("PONG :tmi.twitch.tv")
                continue

            # Account for tags
            ctxs = get_contexts(data)

            for ctx in ctxs:
                await self.manager.queue_ctx(ctx)

    async def connect(self):
        log.info(f"Connecting to irc server as {self.IRC_USERNAME}")
        await self.ws.send(f"PASS {self.IRC_OAUTH}")
        await self.ws.send(f"NICK {self.IRC_USERNAME}")

    async def join(self, channel):
        log.info(f"Joining #{channel}")
        await self.ws.send(f"JOIN #{channel.lower()}")

    async def part(self, channel):
        log.info(f"Leaving #{channel}\r\n")
        await self.ws.send(f"PART #{channel.lower()}\r\n")

    async def register_cap(self, *caps):
        log.info(f"Registering capability '{caps}'")
        caps = ' '.join([f'twitch.tv/{cap}' for cap in caps])
        await self.ws.send(f"CAP REQ :{caps}\r\n")

    async def send_message(self, channel, message):
        message = message.strip()
        while (i := message.find("  ")) != -1:
            message = message[:i] + message[i+1:]

        await self.message_locks[channel].acquire()

        messages = split_message(message)
        for msg in messages:
            log.info(f"Sending message: {msg}")

            await self.ws.send(
                f"PRIVMSG #{channel} :/me " + msg + (" \U000e0000" if self.last_message[channel] == msg else "")
            )

            self.last_message[channel] = msg

            await asyncio.sleep(self.get_wait_for_channel(channel))  # Avoid going over ratelimits

        self.message_locks[channel].release()

        return messages

    # Util

    def call_later(self, wait, callback, *args, **kwargs) -> asyncio.Task:
        return self.loop.create_task(wait_and_call(wait, callback, *args, **kwargs))

    async def create_periodic_message(self, channel, message, wait_time, offset):
        async def send_message():
            await self.send_message(channel, message)
            self.call_later(wait_time, send_message)

        if offset == 0:
            await send_message()
        else:
            self.call_later(offset, send_message)

    def get_wait_for_channel(self, channel):
        # TODO: make a check for if the bot is a moderator in the channel
        if channel == self.IRC_USERNAME or (self.own_state is not None and self.own_state.mod):
            return 0.3
        return 1.5

    # hooks

    async def on_setup(self, ctx):
        log.info("Running setup")
        await self.db.setup()

    async def on_connected(self, ctx):
        log.info("Connected to server")

    async def on_message(self, ctx: MessageContext):
        log.info(f"Message in #{ctx.channel} from {ctx.sending_user}: {ctx.message}")

    async def on_user_state(self, ctx: UserStateContext):
        log.info("Received user state")

    async def on_room_state(self, ctx: RoomStateContext):
        log.info("Received room state")

    async def on_join(self, ctx: JoinContext):
        log.info(f"Joined {ctx.channel}")

    async def on_part(self, ctx: PartContext):
        log.info(f"Parted {ctx.channel}")

    async def on_reconnect(self, ctx):
        log.info("Twitch requested the bot to reconnect")
        self.running.clear()

    async def on_server_msg(self, ctx: ServerMessageContext):
        log.info(f"Received server message: {ctx.data!r}")

    def __getattribute__(self, name):
        try:
            return super().__getattribute__(name)
        except AttributeError as exc:
            if name == "dependencies":
                raise exc

        for dependency in self.dependencies:
            try:
                return getattr(dependency, name)
            except AttributeError:
                continue

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


BOT_CLASSES = []


class BotMeta(type):
    def __new__(cls, name, bases, attrs):
        attrs["dependencies"] = list()
        if "__init__" not in attrs:
            attrs["__init__"] = lambda self: None
        new_cls = type(name, bases, attrs)
        BOT_CLASSES.append(new_cls)
        return new_cls


class BotManager:
    __slots__ = ("bots", "ctx_queue", "base_bot", "running", "loop", "context_handlers")

    def __init__(self, loop: asyncio.AbstractEventLoop):
        bot_classes = list(BOT_CLASSES)

        self.loop = loop
        self.ctx_queue: asyncio.Queue = asyncio.Queue()

        self.base_bot = base_bot = BaseBot(loop, self)
        self.running: asyncio.Event = self.base_bot.running

        self.bots = bots = {
            f"{BaseBot.__module__}.{BaseBot.__name__}": base_bot
        }
        while len(bot_classes) > 0:
            i = 0
            while i < len(bot_classes):
                cls = bot_classes[i]

                dependencies = [f"{dependency.__module__}.{dependency.__name__}" for dependency in cls.__bases__]
                try:
                    dependencies = [bots[dependency] for dependency in dependencies]
                    cls.dependencies.extend(dependencies)
                except KeyError:
                    i += 1
                    continue

                bots[f"{cls.__module__}.{cls.__name__}"] = cls()

                bot_classes.pop(i)

        context_handlers = {
            ContextType.SETUP: "on_setup",
            ContextType.UPDATE: "on_update",
            ContextType.CONNECTED: "on_connected",
            ContextType.JOIN: "on_join",
            ContextType.PART: "on_part",
            ContextType.PRIVMSG: "on_message",
            ContextType.USERSTATE: "on_user_state",
            ContextType.ROOMSTATE: "on_room_state",
            ContextType.RECONNECT: "on_reconnect",
            ContextType.SERVER_MSG: "on_server_msg"
        }
        self.context_handlers = {
            ctx_type: [
                func
                for bot in bots.values()
                if (func := getattr(bot, func_name, None)) is not None and
                func.__func__.__qualname__.split(".")[-2] == func.__self__.__class__.__name__
            ]
            for ctx_type, func_name in context_handlers.items()
        }

    def get_bot_for(self, func):
        return self.bots[f"{func.__module__}.{func.__qualname__.split('.')[-2]}"]

    async def queue_ctx(self, ctx):
        await self.ctx_queue.put(ctx)

    async def run_ctx_handler(self):
        while self.running.is_set():
            ctx = await self.ctx_queue.get()
            for handler in self.context_handlers.get(ctx.type, []):
                if ctx.type == ContextType.SETUP:
                    await handler(ctx)
                else:
                    self.loop.create_task(handler(ctx))

    async def run(self):
        server = MessageServer(self.loop, self.ctx_queue)
        self.loop.create_task(server.run())

        self.running.set()

        await self.ctx_queue.put(UnknownContext(None, ContextType.SETUP))

        while self.running.is_set():
            self.loop.create_task(self.run_ctx_handler())

            restart = await self.base_bot.run()
            if restart:
                self.running.set()
