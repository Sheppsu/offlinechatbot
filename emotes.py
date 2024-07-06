import os
import asyncio
from aiohttp import client_exceptions, ClientSession

from helper_objects import TwitchAPIHelper


class SevenTVFile:
    __slots__ = ("name", "static_name", "width", "height", "frame_count", "size", "format")
    
    def __init__(self, data):
        self.name = data["name"]
        self.static_name = data["static_name"]
        self.width = data["width"]
        self.height = data["height"]
        self.frame_count = data["frame_count"]
        self.size = data["size"]
        self.format = data["format"]


class SevenTVHost:
    __slots__ = (
        "url",
        "files",
    )

    def __init__(self, data):
        self.url = data["url"]
        self.files = list(map(SevenTVFile, data["files"]))
        
        
class SevenTVUser:
    __slots__ = (
        "id",
        "username",
        "display_name",
        "avatar_url",
        "style",
        "roles",
    )
    
    def __init__(self, data):
        self.id = data["id"]
        self.username = data["username"]
        self.display_name = data["display_name"]
        self.avatar_url = data.get("avatar_url")
        self.style = data["style"]
        self.roles = data.get("roles")


class SevenTVEmoteData:
    __slots__ = (
        "id",
        "name",
        "flags",
        "lifecycle",
        "state",
        "listed",
        "animated",
        "owner",
        "host"
    )
    
    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.flags = data["flags"]
        self.lifecycle = data["lifecycle"]
        self.state = data["state"]
        self.listed = data["listed"]
        self.animated = data["animated"]
        self.owner = SevenTVUser(data["owner"])
        self.host = SevenTVHost(data["host"])


class SevenTVEmote:
    __slots__ = (
        "id",
        "name",
        "flags",
        "timestamp",
        "actor_id",
        "data",
    )

    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.flags = data["flags"]
        self.timestamp = data["timestamp"]
        self.actor_id = data["actor_id"]
        self.data = SevenTVEmoteData(data["data"])


class BetterTVEmote:
    __slots__ = (
        "id", "name", "image_type", "owner_id"
    )

    def __init__(self, data):
        self.id = data["id"]
        self.name = data["code"]
        self.image_type = data["imageType"]
        self.owner_id = data["userId"]


class FrankerFaceZUser:
    __slots__ = (
        "id", "name", "display_name",
    )

    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.display_name = data["displayName"]


class FrankerFaceZEmote:
    __slots__ = (
        "id", "owner", "name", "images", "image_type"
    )

    def __init__(self, data):
        self.id = data["id"]
        self.owner = FrankerFaceZUser(data["user"])
        self.name = data["code"]
        self.images = data["images"]
        self.image_type = data["imageType"]


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
        except client_exceptions.ClientError:
            return return_on_error

    async def get(self, path, headers=None, return_on_fail=None, **kwargs):
        headers = {
            "Content-Type": "application/json",
            **(headers if headers is not None else {}),
        }
        headers.update(kwargs.pop("headers", {}))
        return await self.make_request("get", str(path), headers=headers, **kwargs)

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
            print("Failed to get user id for " + username)

        return user_id


def require_channel(on_fail):
    def decorator(func):
        async def wrapper(self, channel):
            if isinstance(channel, str):
                channel = await self.http.get_user_id(channel)
            if channel is None:
                return on_fail()

            return await func(self, channel)

        return wrapper

    return decorator


class EmoteRequester:
    def __init__(self, twitch_client: TwitchAPIHelper):
        self.http: HTTPHandler = HTTPHandler(twitch_client)

    @require_channel(lambda: ([], [], []))
    async def get_channel_emotes(self, channel):
        return sum(await asyncio.gather(
            self.get_7tv_channel_emotes(channel),
            self.get_bttv_channel_emotes(channel),
            self.get_ffz_channel_emotes(channel)
        ), [])

    async def get_global_emotes(self):
        return sum(await asyncio.gather(
            self.get_7tv_global_emotes(),
            self.get_bttv_global_emotes(),
            self.get_ffz_global_emotes()
        ), [])

    @require_channel(lambda: [])
    async def get_7tv_channel_emotes(self, channel):
        return list(map(
            SevenTVEmote,
            (await self.http.get(
                Path.get_7tv_channel_emotes(channel),
                return_on_fail={"emote_set": {"emotes": []}}
            ))["emote_set"]["emotes"]
        ))

    async def get_7tv_global_emotes(self):
        return list(map(
            SevenTVEmote,
            (await self.http.get(
                Path.get_7tv_global_emotes(),
                return_on_fail={"emotes": []}
            ))["emotes"]
        ))

    @require_channel(lambda: [])
    async def get_bttv_channel_emotes(self, channel):
        return list(map(
            BetterTVEmote,
            (await self.http.get(
                Path.get_bttv_channel_emotes(channel),
                return_on_fail={"channelEmotes": []}
            ))["channelEmotes"]
        ))

    async def get_bttv_global_emotes(self):
        return list(map(BetterTVEmote, await self.http.get(Path.get_bttv_global_emotes(), return_on_fail=[])))

    @require_channel(lambda: [])
    async def get_ffz_channel_emotes(self, channel):
        return list(map(FrankerFaceZEmote, await self.http.get(Path.get_ffz_channel_emotes(channel), return_on_fail=[])))

    async def get_ffz_global_emotes(self):
        return list(map(FrankerFaceZEmote, await self.http.get(Path.get_ffz_global_emotes(), return_on_fail=[])))


# Testing
if __name__ == "__main__":
    from dotenv import load_dotenv
    import sys

    load_dotenv()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def main():
        twitch_client = TwitchAPIHelper(os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET"))
        emote_requester = EmoteRequester(twitch_client)
        emotes = await emote_requester.get_channel_emotes("btmc")
        print(f"{len(emotes)} emotes")
        print(f"{len(tuple(filter(lambda e: isinstance(e, SevenTVEmote), emotes)))} 7TV emotes")
        print(f"{len(tuple(filter(lambda e: isinstance(e, BetterTVEmote), emotes)))} BTTV emotes")
        print(f"{len(tuple(filter(lambda e: isinstance(e, FrankerFaceZEmote), emotes)))} FFZ emotes")

    asyncio.new_event_loop().run_until_complete(main())
