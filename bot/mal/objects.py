from .enums import *
from .exceptions import PagingException
from urllib.parse import unquote


class Util:
    @staticmethod
    def float(num):
        if num is None:
            return
        return float(num)

    @staticmethod
    def int(num):
        if num is None:
            return
        return int(num)


class AlternativeTitles:
    __slots__ = ("synonyms", "en", "ja")

    def __init__(self, data):
        self.synonyms = data['synonyms']
        self.en = data['en']
        self.ja = data['ja']


class Picture:
    __slots__ = ("large", "medium")

    def __init__(self, data):
        self.large = data['large']
        self.medium = data['medium']


class Genre:
    __slots__ = ("id", "name")

    def __init__(self, data):
        self.id = data['id']
        self.name = data['name']


class Season:
    __slots__ = ("year", "season")

    def __init__(self, data):
        self.year = data['year']
        self.season = data['season']


class Broadcast:
    __slots__ = ("day_of_the_week", "start_time")

    def __init__(self, data):
        self.day_of_the_week = data['day_of_the_week']
        self.start_time = data['start_time']


class Studio:
    __slots__ = ("id", "name")

    def __init__(self, data):
        self.id = data['id']
        self.name = data['name']


class Anime:
    __slots__ = (
        "id", "title", "main_picture", "alternative_titles",
        "start_date", "end_date", "synopsis", "mean",
        "rank", "popularity", "num_list_users", "num_scoring_users",
        "nsfw", "genres", "created_at", "updated_at", "media_type",
        "status", "my_list_status", "num_episodes", "start_season",
        "broadcast", "source", "average_episode_duration", "rating",
        "studios"
    )

    def __init__(self, data):
        self.id = data.get('id')
        self.title = data.get('title')
        self.main_picture = Picture(data['main_picture']) if data.get("main_picture") is not None else None
        self.alternative_titles = AlternativeTitles(data['alternative_titles']) if data.get('alternative_titles') is not None else None
        self.start_date = data.get('start_date')
        self.end_date = data.get('end_date')
        self.synopsis = data.get('synopsis')
        self.mean = Util.float(data.get('mean'))
        self.rank = Util.int(data.get('rank'))
        self.popularity = Util.int(data.get('popularity'))
        self.num_list_users = Util.int(data.get('num_list_users'))
        self.num_scoring_users = Util.int(data.get('num_scoring_users'))
        self.nsfw = NSFW[data['nsfw'].lower()] if data.get('nsfw') is not None else None
        self.genres = list(map(Genre, data.get('genres'))) if 'genres' in data else None
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.media_type = MediaType[data['media_type']] if data.get('media_type') is not None else None
        self.status = Status[data['status']] if 'status' in data else None
        self.my_list_status = data.get('my_list_status')  # I don't feel like writing out the object for this lole
        self.num_episodes = Util.int(data.get('num_episodes'))
        self.start_season = Season(data['start_season']) if data.get('start_season') is not None else None
        self.broadcast = Broadcast(data['broadcast']) if data.get('broadcast') is not None else None
        self.source = Source[data['source']] if data.get('source') is not None else None
        self.average_episode_duration = Util.int(data.get('average_episode_duration'))
        self.rating = Rating[data['rating'].lower()] if data.get('rating') is not None else None
        self.studios = list(map(Studio, data['studios'])) if 'studios' in data else None


class Ranking:
    __slots__ = (
        "rank", "previous_rank"
    )

    def __init__(self, data):
        self.rank = data.get('rank')
        self.previous_rank = data.get('previous_rank')


class AnimeRanking:
    __slots__ = ("anime", "ranking")

    def __init__(self, data):
        self.anime = Anime(data['node'])
        self.ranking = Ranking(data['ranking'])


class Paging:
    __slots__ = ("previous", "next", "endpoint", "args")

    def __init__(self, data, endpoint):
        self.previous = data.get('previous')
        self.next = data.get('next')
        self.endpoint = endpoint

    def get_next(self, client):
        if self.next is None:
            raise PagingException("Cannot get next because there is none.")
        url = unquote(self.next)
        url_args = dict([arg.split("=") for arg in url[url.index("?")+1:].split("&")])
        return getattr(client, self.endpoint)(**url_args)

    def get_previous(self, client):
        if self.previous is None:
            raise PagingException("Cannot get previous because there is none.")
        url = unquote(self.previous)
        url_args = dict([arg.split("=") for arg in url[url.index("?")+1:].split("&")])
        return getattr(client, self.endpoint)(**url_args)


class Path:
    def __init__(self, method, path):
        self.method = method
        self.path = path

    @classmethod
    def get_anime_ranking(cls):
        return cls("GET", "/anime/ranking")
