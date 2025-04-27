from ...bot import BotMeta
from ..base import CommandBot

from osu import AsynchronousClient
import os


class OsuClientBot(CommandBot, metaclass=BotMeta):
    __slots__ = ("osu_client",)

    def __init__(self):
        self.osu_client: AsynchronousClient = None  # type: ignore

    async def on_setup(self, ctx):
        self.osu_client = await AsynchronousClient.from_client_credentials(
            int(os.getenv("OSU_CLIENT_ID")),
            os.getenv("OSU_CLIENT_SECRET"),
            None,
            request_wait_time=0.7
        )
