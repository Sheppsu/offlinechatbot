import requests
import os
from dotenv import load_dotenv
from time import perf_counter

load_dotenv()


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
        "twitch": "https://api.twitch.tv/helix/",
        "7tv": "https://7tv.io/v3/",
        "bttv": "https://api.betterttv.net/3/",
        "ffz": "https://api.betterttv.net/3/",
    }

    def __init__(self, provider, path, auth=None):
        self.path = self.providers[provider] + path
        self.auth = auth

    @classmethod
    def get_user_id(cls):
        return cls("twitch", "users", "twitch")

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
    def __init__(self, twitch_client_id, twitch_client_secret):
        self.twitch_client_id = twitch_client_id
        self.twitch_client_secret = twitch_client_secret
        self.access_token = None
        self.expire_time = None
        self.user_id_cache = {}

    @property
    def twitch_auth_header(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Client-Id": self.twitch_client_id,
        }

    def set_access_token(self, access_token):
        self.access_token = access_token

    def get_access_token(self):
        params = {
            "client_id": self.twitch_client_id,
            "client_secret": self.twitch_client_secret,
            "grant_type": "client_credentials"
        }
        resp = requests.post("https://id.twitch.tv/oauth2/token", params=params)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"Failed to retrieve access token: {e}")
            return ""
        resp = resp.json()
        self.access_token, self.expire_time = resp['access_token'], resp['expires_in']
        self.expire_time += perf_counter()

    def get(self, path, headers=None, return_on_fail=None, **kwargs):
        headers = {
            "Content-Type": "application/json",
            **(getattr(self, f"{path.auth}_auth_header") if path.auth is not None else {}),
            **(headers if headers is not None else {}),
        }
        resp = requests.get(path, headers=headers, **kwargs)

        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"Failed request for {path}: {e}")
            return return_on_fail

        return resp.json()

    def get_user_id(self, username):
        if username in self.user_id_cache:
            return self.user_id_cache[username]
        data = self.get(Path.get_user_id(), params={"login": username}, return_on_fail={"data": [{"id": None}]})["data"]
        if not data:
            return
        user_id = int(data[0]["id"])
        if user_id is not None:
            self.user_id_cache[username] = user_id
        else:
            print("Failed to get user id for " + username)
        return user_id


class EmoteRequester:
    def __init__(self, twitch_client_id, twitch_client_secret):
        self.http = HTTPHandler(twitch_client_id, twitch_client_secret)

    def get_channel_emotes(self, channel):
        if channel is None: return [], [], []
        if type(channel) == str: channel = self.http.get_user_id(channel)
        return self.get_7tv_channel_emotes(channel), \
               self.get_bttv_channel_emotes(channel), \
               self.get_ffz_channel_emotes(channel)

    def get_global_emotes(self):
        return self.get_7tv_global_emotes(), \
               self.get_bttv_global_emotes(), \
               self.get_ffz_global_emotes()

    def get_7tv_channel_emotes(self, channel):
        if channel is None: return []
        if type(channel) == str: channel = self.http.get_user_id(channel)
        if channel is None: return []
        data = self.http.get(Path.get_7tv_channel_emotes(channel), return_on_fail=None)
        if data is None:
            return []
        return list(map(SevenTVEmote, data["emote_set"]["emotes"]))

    def get_7tv_global_emotes(self):
        data = self.http.get(Path.get_7tv_global_emotes(), return_on_fail=None)
        if data is None:
            return []
        return list(map(SevenTVEmote, data["emotes"]))

    def get_bttv_channel_emotes(self, channel):
        if channel is None: return []
        if type(channel) == str: channel = self.http.get_user_id(channel)
        if channel is None: return []
        return list(map(BetterTVEmote, self.http.get(Path.get_bttv_channel_emotes(channel), return_on_fail={"channelEmotes": []})["channelEmotes"]))

    def get_bttv_global_emotes(self):
        return list(map(BetterTVEmote, self.http.get(Path.get_bttv_global_emotes(), return_on_fail=[])))

    def get_ffz_channel_emotes(self, channel):
        if channel is None: return []
        if type(channel) == str: channel = self.http.get_user_id(channel)
        if channel is None: return []
        return list(map(FrankerFaceZEmote, self.http.get(Path.get_ffz_channel_emotes(channel), return_on_fail=[])))

    def get_ffz_global_emotes(self):
        return list(map(FrankerFaceZEmote, self.http.get(Path.get_ffz_global_emotes(), return_on_fail=[])))


# Testing
if __name__ == "__main__":
    emote_requester = EmoteRequester(os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET"))
    emote_requester.http.get_access_token()
    emotes = emote_requester.get_channel_emotes("btmc")
    print(emotes[0])
    print(emotes[1])
    print(emotes[2])
