import requests
import json

from .constants import azur_lane_data_url, name_formatting


def format_name(name):
    new_name = ""
    for char in name:
        new_name += name_formatting[char] if char in name_formatting else char
    return new_name


def download_azur_lane_ship_names():
    r = requests.get(azur_lane_data_url)
    data = r.json()
    ships = []
    for shipdata in data.values():
        name = shipdata["english_name"]
        if name not in ships:
            ships.append(name)
    ships = list(map(format_name, ships))
    for ship in ships:
        for char in ship:
            if not char.isascii():
                print(char)
    with open("data/azur_lane.json", "w") as f:
        json.dump(ships, f)
