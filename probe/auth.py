"""Auth manager: login, token storage, background refresh."""

import threading
import time

import httpx


class AuthError(Exception):
    pass


class AuthManager:
    REFRESH_INTERVAL = 55 * 60  # 55 minutes

    def __init__(self, base_url: str, email: str, password: str):
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._token: str | None = None
        self._lock = threading.Lock()
        self._refresh_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def login(self) -> str:
        url = f"{self._base_url}/api/v2/system/users/login"
        try:
            r = httpx.post(
                url,
                json={"email": self._email, "password": self._password},
                verify=False,
                timeout=30,
            )
            r.raise_for_status()
            token = r.json()["data"]["token"]
        except httpx.HTTPStatusError as e:
            raise AuthError(
                f"Login failed (HTTP {e.response.status_code}): {e.response.text[:200]}"
            )
        except Exception as e:
            raise AuthError(f"Login error: {e}")

        with self._lock:
            self._token = token
        return token

    def refresh(self) -> str:
        with self._lock:
            token = self._token
        if not token:
            return self.login()

        url = f"{self._base_url}/api/v2/system/users/token/refresh"
        try:
            r = httpx.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                verify=False,
                timeout=30,
            )
            r.raise_for_status()
            new_token = r.json()["data"]["token"]
        except Exception:
            # Fall back to full re-login
            return self.login()

        with self._lock:
            self._token = new_token
        return new_token

    def get_token(self) -> str:
        with self._lock:
            if self._token:
                return self._token
        return self.login()

    def start_auto_refresh(self):
        self._stop_event.clear()

        def _worker():
            while not self._stop_event.wait(self.REFRESH_INTERVAL):
                try:
                    self.refresh()
                except Exception:
                    pass  # next iteration will retry

        self._refresh_thread = threading.Thread(target=_worker, daemon=True)
        self._refresh_thread.start()

    def stop_auto_refresh(self):
        self._stop_event.set()
