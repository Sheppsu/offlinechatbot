import requests
from .constants import API_URL


class HttpHandler:
    def __init__(self, auth):
        self.auth = auth

    def request(self, path, headers=None, **params):
        if headers is None:
            headers = {}
        headers.update(self.auth.auth_header)
        method = getattr(requests, path.method.lower())
        resp = method(API_URL+path.path, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
