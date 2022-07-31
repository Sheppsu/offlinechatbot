import websockets
import json
import asyncio
import requests
from os import getenv


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
        print(f"> AUTH {self.PASSWORD}")
        await self.ws.send("CONNTYPE " + self.CONN_TYPE)
        print(f"> CONNTYPE {self.CONN_TYPE}")

    async def close(self):
        await self.ws.close(1000)

    async def poll(self):
        while True:
            data = await self.ws.recv()
            print(f"< {data}")
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
        except websockets.ConnectionClosedError as err:
            if err.rcvd is None:
                return print(err)
            print(err.rcvd.reason)
            if err.rcvd.code == 3001 or str(err) == self.last_err:
                await asyncio.sleep(60)
            else:
                self.last_err = str(err)
        except Exception as e:
            print(e)
            if self.last_err == str(e):
                await asyncio.sleep(60)
            self.last_err = str(e)
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
        data = data.split()
        client_id = data[0]
        command = data[1].upper()
        params = {}
        if len(data) > 2:
            params = json.loads(" ".join(data[2:]))

        print(f"Message received from client {client_id}: {command} {params if params else ''}")
        if command in self.command_handlers:
            asyncio.run_coroutine_threadsafe(self.command_handlers[command](client_id, params), self.bot.loop)

    async def on_refresh_db(self, client_id, params):
        self.bot.reload_db_data()
        await self.ws.send(f"{client_id} REFRESHDB OK")
        print(f"> {client_id} REFRESHDB OK")

    async def on_channel_reload(self, client_id, params):
        self.bot.reload_channels()
        await self.ws.send(f"{client_id} RELOAD_CHANNELS OK")
        print(f"> {client_id} RELOAD_CHANNELS OK")
