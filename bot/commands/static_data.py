from .base import CommandBot
from ..bot import BotMeta

import json


class StaticDataBot(CommandBot, metaclass=BotMeta):
    __slots__ = (
        "word_list",
        "top_players",
        "top_maps",
        "genshin",
        "azur_lane",
        "all_words",
        "anime",
        "pull_options"
    )

    command_manager = CommandBot.command_manager

    def __init__(self):
        with open("data/words.json", "r") as f:
            self.word_list: list[str] = json.load(f)
        with open("data/top players (200).json", "r") as f:
            self.top_players: list[str] = json.load(f)
        with open("data/top_maps.json", "r") as f:
            self.top_maps: list[str] = json.load(f)
        with open("data/genshin.json", "r") as f:
            self.pull_options: dict[str, list[str]] = json.load(f)
        with open("data/azur_lane.json", "r") as f:
            self.azur_lane: list[str] = json.load(f)
        with open("data/all_words.json", "r") as f:
            self.all_words: list[str] = [word.lower() for word in json.load(f)]
        with open("data/anime.json", "r") as f:
            self.anime: list[str] = json.load(f)

        self.genshin = self.pull_options["3"] + self.pull_options["4"] + self.pull_options["5"]
