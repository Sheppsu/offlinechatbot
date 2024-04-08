import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

lastfm_token = os.getenv("LASTFM_TOKEN")


class LastFM():
    def __init__(self):
        self.lastfm_token = lastfm_token

    async def get_lastfm_user(self, user):
        self.params = {
            'api_key': self.lastfm_token,
            'user': user,
            'method': 'user.getinfo',
            'format': 'json'
        }
        response = requests.get(
                'http://ws.audioscrobbler.com/2.0/', params=self.params)

        if response.status_code == 200:
            response_json = json.loads(response.text)
            return response.json()
        
        else:
            return None

    def get_recent_song(self, user):
        self.params = {
            'method': 'user.getrecenttracks',
            'user': user,
            'api_key': self.lastfm_token,
            'extended': 1,
            'limit': 1,
            'format': 'json',
        }
        response = requests.get(
            'http://ws.audioscrobbler.com/2.0/', params=self.params)
        print(f"Response json: {response.json()}")
        return response.json()
