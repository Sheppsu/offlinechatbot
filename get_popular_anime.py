from mal import Client
import os
import json
import sys


if "--test" in sys.argv:
    from dotenv import load_dotenv
    load_dotenv()


client = Client.from_client_credentials(os.getenv("MAL_CLIENT_ID"), os.getenv("MAL_CLIENT_SECRET"))

paging = None
ranking = []
for _ in range(10):
    if paging is None:
        r, paging = client.get_anime_ranking("bypopularity", fields="title,alternative_titles{en}")
    else:
        r, paging = paging.get_next(client)
    ranking += r


def format_title(title):
    return "".join([char for char in title if char.isascii()])


with open("data/anime.json", "w") as f:
    json.dump(list(map(lambda r: format_title(r.anime.alternative_titles.en if r.anime.alternative_titles.en is not None else r.anime.title), ranking)), f)
