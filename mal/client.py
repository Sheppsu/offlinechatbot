from .auth import AuthorizationHandler
from .http import HttpHandler
from .objects import *


class Client:
    def __init__(self, auth):
        self.http = HttpHandler(auth)

    @classmethod
    def from_client_credentials(cls, client_id, client_secret):
        return cls(AuthorizationHandler(client_id, client_secret))

    def get_anime_ranking(self, ranking_type='all', limit=100, offset=0, fields=None):
        path = Path.get_anime_ranking()
        resp = self.http.request(path, ranking_type=ranking_type,
                                 limit=limit, offset=offset, fields=fields)
        return list(map(AnimeRanking, resp['data'])), Paging(resp['paging'], "get_anime_ranking")
