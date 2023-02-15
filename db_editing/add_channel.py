"""
Meant to be moved to the main directory when running
"""
import sys
import os
import requests
from dotenv import load_dotenv
load_dotenv()


CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")


def get_twitch_access_token():
    params = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    resp = requests.post("https://id.twitch.tv/oauth2/token", params=params)
    resp.raise_for_status()
    resp = resp.json()
    return resp['access_token']


def get_headers(access_token):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Client-Id": CLIENT_ID,
    }


def get_userid_from_username(access_token, username):
    headers = get_headers(access_token)
    params = {"login": username}
    resp = requests.get("https://api.twitch.tv/helix/users", headers=headers, params=params)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Failed to get user id for {username}: {e}")
    try:
        return resp.json()["data"][0]["id"]
    except IndexError:
        print(f"Could not find userid for {username}")


access_token = get_twitch_access_token()
channel = sys.argv[1]
channel_id = get_userid_from_username(access_token, channel)
if channel_id is None:
    print("Could not resolve channel name to channel id")
    quit()
inclusion = int(sys.argv[2])
offlineonly = int(sys.argv[3])
commands = sys.argv[4]
print(commands)


from sql import Database


db = Database()
db.add_channel(channel, channel_id, inclusion, offlineonly, commands)
