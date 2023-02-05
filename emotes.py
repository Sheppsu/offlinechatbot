import requests
import os
from dotenv import load_dotenv
from time import perf_counter

load_dotenv()


class SevenTVRole:
    __slots__ = (
        "id", "name", "position", "color", "allowed", "denied", "default"
    )

    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.position = data["position"]
        self.color = data["color"]
        self.allowed = data["allowed"]
        self.denied = data["denied"]
        self.default = data["default"] if "default" in data else False


class SevenTVUser:
    __slots__ = (
        "id", "twitch_id", "login", "display_name", "role"
    )

    def __init__(self, data):
        self.id = data["id"]
        self.twitch_id = data["twitch_id"]
        self.login = data["login"]
        self.display_name = data["display_name"]
        self.role = SevenTVRole(data["role"])


class SevenTVEmote:
    __slots__ = (
        "id", "name", "owner", "visibility", "visibility_simple",
        "mime", "status", "tags", "width", "height", "urls"
    )

    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.owner = SevenTVUser(data["owner"])
        self.visibility = data["visibility"]
        self.visibility_simple = data["visibility_simple"]
        self.mime = data["mime"]
        self.status = data["status"]
        self.tags = data["tags"]
        self.width = data["width"]
        self.height = data["height"]
        self.urls = data["urls"]


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
        "7tv": "https://api.7tv.app/v2/",
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
        return cls("7tv", f"users/{channel}/emotes")

    @classmethod
    def get_7tv_global_emotes(cls):
        return cls("7tv", "emotes/global")

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
        self._access_token, self.expire_time = self.get_access_token()
        self.expire_time += perf_counter()
        self.user_id_cache = {}

    @property
    def access_token(self):
        if self.expire_time <= perf_counter():
            self._access_token, self.expire_time = self.get_access_token()
        return self._access_token

    @property
    def twitch_auth_header(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Client-Id": self.twitch_client_id,
        }

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
        return resp['access_token'], resp['expires_in']

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
        user_id = self.get(Path.get_user_id(), params={"login": username}, return_on_fail={"data": [{"id": None}]})["data"][0]["id"]
        if user_id is not None:
            self.user_id_cache[username] = user_id
        else:
            print("Failed to get user id for " + username)
        return user_id


class EmoteRequester:
    def __init__(self, twitch_client_id, twitch_client_secret):
        self.http = HTTPHandler(twitch_client_id, twitch_client_secret)

    def get_channel_emotes(self, channel):
        return self.get_7tv_channel_emotes(channel), \
               self.get_bttv_channel_emotes(channel), \
               self.get_ffz_channel_emotes(channel)

    def get_global_emotes(self):
        return self.get_7tv_global_emotes(), \
               self.get_bttv_global_emotes(), \
               self.get_ffz_global_emotes()

    def get_7tv_channel_emotes(self, channel):
        return list(map(SevenTVEmote, self.http.get(Path.get_7tv_channel_emotes(channel), return_on_fail=[])))

    def get_7tv_global_emotes(self):
        return list(map(SevenTVEmote, self.http.get(Path.get_7tv_global_emotes(), return_on_fail=[])))

    def get_bttv_channel_emotes(self, channel):
        return list(map(BetterTVEmote, self.http.get(Path.get_bttv_channel_emotes(self.http.get_user_id(channel)), return_on_fail={"channelEmotes": []})["channelEmotes"]))

    def get_bttv_global_emotes(self):
        return list(map(BetterTVEmote, self.http.get(Path.get_bttv_global_emotes(), return_on_fail=[])))

    def get_ffz_channel_emotes(self, channel):
        return list(map(FrankerFaceZEmote, self.http.get(Path.get_ffz_channel_emotes(self.http.get_user_id(channel)), return_on_fail=[])))

    def get_ffz_global_emotes(self):
        return list(map(FrankerFaceZEmote, self.http.get(Path.get_ffz_global_emotes(), return_on_fail=[])))


# Testing
if __name__ == "__main__":
    emote_requester = EmoteRequester(os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET"))
    emotes = emote_requester.get_channel_emotes("btmc")
    print(emotes[0][0])
    print(emotes[1][0])
    print(emotes[2][0])
