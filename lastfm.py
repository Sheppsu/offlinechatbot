import requests
import os


lastfm_token = os.getenv("LASTFM_API_KEY")


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
            print(f"Lastfm request failed: {err}\n{resp.text}")

    def get_lastfm_user(self, user):
        params = self.get_params("user.getinfo", user=user)
        resp = requests.get("http://ws.audioscrobbler.com/2.0/", params=params)
        return self.return_response(resp)

    def get_recent_song(self, user):
        params = self.get_params("user.getrecenttracks", user=user, extended=1, limit=1)
        resp = requests.get("http://ws.audioscrobbler.com/2.0/", params)
        return self.return_response(resp)
