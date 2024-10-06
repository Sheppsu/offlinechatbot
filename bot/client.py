import websockets
import json
import asyncio
import requests
import logging
from os import getenv

from .util import future_callback


log = logging.getLogger(__name__)


class ClientBase:
    HOST = getenv('COMM_HOST')
    PORT = int(getenv('COMM_PORT'))
    URI = f"wss://{HOST}:{PORT}"
    PASSWORD = getenv('COMM_PASS')
    CONN_TYPE = None

    def __init__(self):
        self.ws = None
        self.last_err = None

    async def make_connection(self):
        await self.ws.send("AUTH " + self.PASSWORD)
        log.info(f"> AUTH {self.PASSWORD}")
        await self.ws.send("CONNTYPE " + self.CONN_TYPE)
        log.info(f"> CONNTYPE {self.CONN_TYPE}")

    async def close(self):
        await self.ws.close(1000)

    async def poll(self):
        while True:
            data = await self.ws.recv()
            log.info(f"< {data}")
            await self.handle_data(data)

    async def handle_data(self, data):
        raise NotImplementedError()

    def check_server_health(self):
        r = requests.get(f"https://{self.HOST}/health")
        return r.status_code == 200

    async def run(self):
        while not self.check_server_health():
            await asyncio.sleep(30)
        try:
            async with websockets.connect(self.URI) as ws:
                self.ws = ws
                await self.make_connection()
                await self.poll()
        except websockets.ConnectionClosedError as exc:
            if exc.rcvd is None:
                log.exception(exc)
            else:
                log.error(exc.rcvd.reason)
                if exc.rcvd.code == 3001 or str(exc) == self.last_err:
                    await asyncio.sleep(60)
                else:
                    self.last_err = str(exc)
        except Exception as exc:
            log.exception(exc)
            if self.last_err == str(exc):
                await asyncio.sleep(60)
            self.last_err = str(exc)
        await self.run()


class Bot(ClientBase):
    # TODO: restart websocket connection if something happens
    CONN_TYPE = "bot"

    def __init__(self, bot):
        self.bot = bot
        super().__init__()

        self.command_handlers = {
            "REFRESHDB": self.on_refresh_db,
            "RELOAD_CHANNELS": self.on_channel_reload,
        }

    async def handle_data(self, data):
        if data == "PING":
            return await self.ws.send("PONG")

        data = data.split()
        client_id = data[0]
        command = data[1].upper()
        params = {}
        if len(data) > 2:
            params = json.loads(" ".join(data[2:]))

        log.info(f"Message received from client {client_id}: {command} {params if params else ''}")

        if command in self.command_handlers:
            future = asyncio.run_coroutine_threadsafe(self.command_handlers[command](client_id, params), self.bot.loop)
            future.add_done_callback(future_callback)

    async def on_refresh_db(self, client_id, params):
        self.bot.reload_db_data()
        await self.ws.send(f"{client_id} REFRESHDB OK")
        log.info(f"> {client_id} REFRESHDB OK")

    async def on_channel_reload(self, client_id, params):
        await self.bot.reload_channels()
        await self.ws.send(f"{client_id} RELOAD_CHANNELS OK")
        log.info(f"> {client_id} RELOAD_CHANNELS OK")
