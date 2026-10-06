"""Thin wrapper around httpx with retry logic and auth injection."""

import time

import httpx


class HttpClient:
    ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]

    def __init__(self, auth_manager, timeout: int = 30, delay: float = 0.0):
        self._auth = auth_manager
        self._timeout = timeout
        self._delay = delay
        self._client = httpx.Client(verify=False, timeout=timeout)

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Send a request with auth header, retrying on 429/5xx/connection errors."""
        kwargs.setdefault("headers", {})
        max_retries = 3
        for attempt in range(max_retries + 1):
            kwargs["headers"]["Authorization"] = f"Bearer {self._auth.get_token()}"
            try:
                resp = self._client.request(method, url, **kwargs)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", "5"))
                    if attempt < max_retries:
                        time.sleep(wait)
                        continue
                elif resp.status_code >= 500 and attempt < 2:
                    time.sleep(2)
                    continue
                if self._delay > 0:
                    time.sleep(self._delay)
                return resp
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
                if attempt < 2:
                    time.sleep(3)
                    continue
                raise
        return resp  # last attempt result

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
