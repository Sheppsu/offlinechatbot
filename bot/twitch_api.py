import asyncio
import logging
from time import monotonic
from aiohttp import ClientSession, client_exceptions


log = logging.getLogger(__name__)


class TwitchAPIHelper:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id: str = client_id
        self.client_secret: str = client_secret
        self._token: str | None = None
        self._expires_at: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def get_token(self) -> str | None:
        await self._lock.acquire()
        # try just in case
        try:
            if monotonic() >= self._expires_at - 5:
                await self._get_token()
        except Exception as exc:
            log.exception("Exception occurred trying to renew twitch api token", exc)
            self._lock.release()
            return

        self._lock.release()

        return self._token

    async def _get_token(self):
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }

        while True:
            data = await self.make_request(
                "post",
                "https://id.twitch.tv/oauth2/token",
                False,
                params=params
            )

            if data is None:
                await asyncio.sleep(1)
                continue

            self._token = data["access_token"]
            self._expires_at = monotonic() + (data["expires_in"] / 1000)

            break

    async def make_request(self, method, url, requires_auth: bool = True, return_on_error=None, **kwargs):
        if requires_auth:
            token = await self.get_token()
            if token is None:
                return return_on_error

            headers = {"Authorization": f"Bearer {token}", "Client-Id": self.client_id}
        else:
            headers = {}
        headers.update(kwargs.pop("headers", {}))

        try:
            async with ClientSession() as session:
                async with session.request(method, url, headers=headers, **kwargs) as resp:
                    data = await resp.json()
                    if "error" in data:
                        log.error(f"Request to {url} failed: {data['error']}")
                        return return_on_error

                    return data
        except client_exceptions.ClientError:
            return return_on_error

    async def get(self, endpoint, return_on_error=None, **kwargs):
        return await self.make_request(
            "get",
            "https://api.twitch.tv/" + endpoint,
            return_on_error=return_on_error,
            **kwargs
        )
