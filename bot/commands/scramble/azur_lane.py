import requests
import json


azur_lane_data_url = "https://raw.githubusercontent.com/AzurLaneTools/AzurLaneData/main/EN/sharecfgdata/ship_data_statistics.json"
name_formatting = {
    "\u00b7": " ",
    "\u014C": "Oo",
    "\u014D": "oo",
    "\u00F6": "o",
    "\u016A": "Uu",
    "\u016B": "uu",
    "\u00FC": "u",
    "\u00DF": "ss",
    "\u00E8": "e",
    "\u00E9": "e",
    "\u00C9": "E",
    "\u00E2": "a",
    "\u00C4": "A",
}


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
