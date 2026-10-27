"""Thin wrapper around httpx with retry logic and auth injection."""

import time
from datetime import datetime, timezone

import httpx


class HttpClient:
    ALL_METHODS = ["GET", "POST", "PUT", "DELETE"]

    def __init__(self, auth_manager, timeout: int = 30, delay: float = 0.0, trace: bool = False):
        self._auth = auth_manager
        self._timeout = timeout
        self._delay = delay
        self._trace = trace
        self._trace_log: list[dict] = []
        self._client = httpx.Client(verify=False, timeout=timeout)

    _HUNTER_NOT_READY_MAX = 5

    def _is_hunter_not_ready(self, resp: httpx.Response) -> bool:
        try:
            return resp.json().get("err") == "Hunter not ready to fly."
        except Exception:
            return False

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Send a request with auth header, retrying on 429/5xx/connection errors."""
        kwargs.setdefault("headers", {})
        max_retries = 3
        hunter_retries = 0
        for attempt in range(max_retries + 1):
            kwargs["headers"]["Authorization"] = f"Bearer {self._auth.get_token()}"
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3] if self._trace else None
            try:
                resp = self._client.request(method, url, **kwargs)
                self._client.cookies.clear()
                if self._trace:
                    self._record(ts, method, url, kwargs, resp, attempt)
                if resp.status_code == 401 and attempt < max_retries:
                    self._auth.refresh()
                    continue
                elif resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", "5"))
                    if attempt < max_retries:
                        time.sleep(wait)
                        continue
                elif resp.status_code >= 500 and attempt < 2:
                    time.sleep(2)
                    continue
                elif self._is_hunter_not_ready(resp) and hunter_retries < self._HUNTER_NOT_READY_MAX:
                    hunter_retries += 1
                    time.sleep(2)
                    continue
                if self._delay > 0:
                    time.sleep(self._delay)
                return resp
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                if self._trace:
                    self._record(ts, method, url, kwargs, None, attempt, error=str(e))
                if attempt < 2:
                    time.sleep(3)
                    continue
                raise
        return resp  # last attempt result

    def _record(self, ts: str, method: str, url: str, kwargs: dict, resp, attempt: int, error: str = None):
        req_headers = dict(kwargs.get("headers", {}))
        auth = req_headers.get("Authorization", "")
        if auth.startswith("Bearer ") and len(auth) > 25:
            req_headers["Authorization"] = auth[:15] + "…" + auth[-6:]

        status = None
        resp_headers = {}
        resp_body = None
        if resp is not None:
            status = resp.status_code
            resp_headers = dict(resp.headers)
            try:
                resp_body = resp.json()
            except Exception:
                text = resp.text
                resp_body = text if text else None

        self._trace_log.append({
            "ts": ts,
            "method": method,
            "url": url,
            "req_headers": req_headers,
            "req_body": kwargs.get("json"),
            "status": status,
            "resp_headers": resp_headers,
            "resp_body": resp_body,
            "retry": attempt,
            "error": error,
        })

    def get_trace(self) -> list[dict]:
        return list(self._trace_log)

    def close(self):
        self._client.close()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
