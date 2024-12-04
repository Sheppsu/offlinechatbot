import asyncio
import logging
from aiohttp import client_exceptions, ClientSession

from ...twitch_api import TwitchAPIHelper


log = logging.getLogger(__name__)


def get_7tv_name(data):
    return data["name"]


def get_ffz_name(data):
    return data["code"]


def get_bttv_name(data):
    return data["code"]


class Path:
    providers = {
        "7tv": "https://7tv.io/v3/",
        "bttv": "https://api.betterttv.net/3/",
        "ffz": "https://api.betterttv.net/3/",
    }

    def __init__(self, provider, path, auth=None):
        self.path = self.providers[provider] + path
        self.auth = auth

    @classmethod
    def get_7tv_channel_emotes(cls, channel):
        return cls("7tv", f"users/twitch/{channel}")

    @classmethod
    def get_7tv_global_emotes(cls):
        return cls("7tv", "emote-sets/global")

    @classmethod
    def get_bttv_channel_emotes(cls, channel):
        return cls("bttv", f"cached/users/twitch/{channel}")

    @classmethod
    def get_bttv_global_emotes(cls):
        return cls("bttv", "cached/emotes/global")

    @classmethod
    def get_ffz_channel_emotes(cls, channel):
        return cls("ffz", f"cached/frankerfacez/users/twitch/{channel}")

    @classmethod
    def get_ffz_global_emotes(cls):
        return cls("ffz", "cached/frankerfacez/emotes/global")

    def __str__(self):
        return self.path


class HTTPHandler:
    def __init__(self, twitch_client: TwitchAPIHelper):
        self.twitch_client: TwitchAPIHelper = twitch_client
        self.user_id_cache: dict[str, int] = {}

    async def make_request(self, method, url, return_on_error=None, **kwargs):
        try:
            async with ClientSession() as session:
                async with session.request(method, url, **kwargs) as resp:
                    return await resp.json()
        except client_exceptions.ClientError as exc:
            log.exception(exc)
            return return_on_error

    async def get(self, path, headers=None, return_on_fail=None, **kwargs):
        headers = {
            "Content-Type": "application/json",
            **(headers if headers is not None else {}),
        }
        headers.update(kwargs.pop("headers", {}))
        return await self.make_request(
            "get",
            str(path),
            headers=headers,
            return_on_error=return_on_fail,
            **kwargs
        )

    async def get_user_id(self, username):
        if username in self.user_id_cache:
            return self.user_id_cache[username]

        data = await self.twitch_client.get(
            "helix/users",
            params={"login": username},
            return_on_error={"data": [{"id": None}]}
        )

        user_id = data["data"][0]["id"]
        if user_id is not None:
            user_id = int(user_id)
            self.user_id_cache[username] = user_id
        else:
            log.error("Failed to get user id for " + username)

        return user_id


def catch_error(on_fail, require_channel=False):
    def decorator(func):
        async def wrapper(self, *args):
            if require_channel:
                channel = args[0]
                if isinstance(channel, str):
                    channel = await self.http.get_user_id(channel)
                if channel is None:
                    return on_fail()

                args = (channel,)

            try:
                return await func(self, *args)
            except KeyError as exc:
                return on_fail()

        return wrapper

    return decorator


class EmoteRequester:
    def __init__(self, twitch_client: TwitchAPIHelper):
        self.http: HTTPHandler = HTTPHandler(twitch_client)

    @catch_error(lambda: [], True)
    async def get_channel_emotes(self, channel):
        return sum(await asyncio.gather(
            self.get_7tv_channel_emotes(channel),
            self.get_bttv_channel_emotes(channel),
            self.get_ffz_channel_emotes(channel)
        ), [])

    @catch_error(lambda: [])
    async def get_global_emotes(self):
        return sum(await asyncio.gather(
            self.get_7tv_global_emotes(),
            self.get_bttv_global_emotes(),
            self.get_ffz_global_emotes()
        ), [])

    @catch_error(lambda: [], True)
    async def get_7tv_channel_emotes(self, channel):
        return list(map(
            get_7tv_name,
            (await self.http.get(
                Path.get_7tv_channel_emotes(channel),
                return_on_fail={"emote_set": {"emotes": []}}
            ))["emote_set"]["emotes"]
        ))

    @catch_error(lambda: [])
    async def get_7tv_global_emotes(self):
        return list(map(
            get_7tv_name,
            (await self.http.get(
                Path.get_7tv_global_emotes(),
                return_on_fail={"emotes": []}
            ))["emotes"]
        ))

    @catch_error(lambda: [], True)
    async def get_bttv_channel_emotes(self, channel):
        return list(map(
            get_bttv_name,
            (await self.http.get(
                Path.get_bttv_channel_emotes(channel),
                return_on_fail={"channelEmotes": []}
            ))["channelEmotes"]
        ))

    @catch_error(lambda: [])
    async def get_bttv_global_emotes(self):
        return list(map(get_bttv_name, await self.http.get(Path.get_bttv_global_emotes(), return_on_fail=[])))

    @catch_error(lambda: [], True)
    async def get_ffz_channel_emotes(self, channel):
        return list(map(get_ffz_name, await self.http.get(Path.get_ffz_channel_emotes(channel), return_on_fail=[])))

    @catch_error(lambda: [])
    async def get_ffz_global_emotes(self):
        return list(map(get_ffz_name, await self.http.get(Path.get_ffz_global_emotes(), return_on_fail=[])))
