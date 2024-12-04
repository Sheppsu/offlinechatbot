from .base import CommandBot, CommandArg
from ..bot import BotMeta

import requests
import os
import logging


lastfm_token = os.getenv("LASTFM_API_KEY")
log = logging.getLogger(__name__)


class LastFMClient:
    def __init__(self):
        self.lastfm_token = lastfm_token

    def get_params(self, method, **kwargs):
        return {
            "api_key": self.lastfm_token,
            "method": method,
            "format": "json",
            **kwargs
        }

    def return_response(self, resp):
        try:
            resp.raise_for_status()
            return resp.json()
        except Exception as err:
            log.error(f"Lastfm request failed: {err}\n{resp.text}")

    def get_lastfm_user(self, user):
        params = self.get_params("user.getinfo", user=user)
        resp = requests.get("http://ws.audioscrobbler.com/2.0/", params=params)
        return self.return_response(resp)

    def get_recent_song(self, user):
        params = self.get_params("user.getrecenttracks", user=user, extended=1, limit=1)
        resp = requests.get("http://ws.audioscrobbler.com/2.0/", params)
        return self.return_response(resp)


class LastFMBot(CommandBot, metaclass=BotMeta):
    __slots__ = ("lastfm",)

    command_manager = CommandBot.command_manager

    def __init__(self):
        self.lastfm = LastFMClient()

    @command_manager.command(
        "lastfm_link",
        "Link your last fm account.",
        [
            CommandArg("username", "lastfm username to link")
        ],
        aliases=["fmlink"]
    )
    async def link_lastfm(self, ctx):
        args = ctx.get_args('ascii')
        if len(args) == 0 or args[0].strip() == "":
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Please specify a username.")

        username = " ".join(args).strip()
        user = self.lastfm.get_lastfm_user(username)

        if user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")

        username = user['user']['name']
        await self.db.set_lastfm(ctx.user_id, ctx.sending_user, username)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Linked {username} to your account.")

    @command_manager.command(
        "lastfm_np",
        "Link current song playing on your lastfm account. Must have linked your lastfm account with !lastfm_link",
        aliases=["fmnp"]
    )
    async def lastfm_np(self, ctx):
        lastfm_user = await self.db.get_lastfm(ctx.user_id)
        if lastfm_user is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You don't have a username linked to LastFM, "
                f"you can do !fmlink *username* to link your account."
            )

        recent_song = self.lastfm.get_recent_song(lastfm_user.username)

        if "@attr" in recent_song['recenttracks']['track'][0]:
            song_title = recent_song['recenttracks']['track'][0]['name']
            song_artist = recent_song['recenttracks']['track'][0]['artist']['name']
            song_url = recent_song['recenttracks']['track'][0]['url']
            return await self.send_message(
                ctx.channel,
                f"Now playing for {lastfm_user.username}: {song_artist} - {song_title} | {song_url}"
            )

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} You are not currently playing anything.")
