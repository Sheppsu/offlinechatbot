import asyncio
import os
import logging
import json

from .context import ServerMessageContext


log = logging.getLogger(__name__)


class MessageProtocol(asyncio.Protocol):
    __slots__ = ("loop", "ctx_queue", "transport")

    def __init__(self, loop: asyncio.AbstractEventLoop, ctx_queue: asyncio.Queue):
        self.loop: asyncio.AbstractEventLoop = loop
        self.ctx_queue: asyncio.Queue = ctx_queue

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data: bytes):
        self.loop.create_task(self.ctx_queue.put(ServerMessageContext(json.loads(data.decode("utf-8")))))

        self.transport.close()


class MessageServer:
    __slots__ = ("loop", "ctx_queue")

    PORT = os.getenv("SERVER_PORT")

    def __init__(self, loop: asyncio.AbstractEventLoop, ctx_queue: asyncio.Queue):
        self.loop: asyncio.AbstractEventLoop = loop
        self.ctx_queue = ctx_queue

    async def run(self):
        server = await self.loop.create_server(
            lambda: MessageProtocol(self.loop, self.ctx_queue),
            host="localhost",
            port=self.PORT
        )

        log.info(f"Receiving messages on port {self.PORT}")

        async with server:
            await server.serve_forever()
