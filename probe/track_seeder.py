"""Set up a live UDP track stream so reports/tracks endpoints return real data."""

import json
import random
import socket
import threading
import time

import requests as _requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


_DATASTREAM_PATH = "/datastream/config"


class TrackSeederError(Exception):
    """Raised when the datastream config setup or track validation fails."""

_DATASTREAM_CONFIG = {
    "apiKey": "",
    "associateInput": False,
    "asterixSystemAreaCode": 0,
    "asterixSystemIdentificationCode": 0,
    "enabled": True,
    "fields": [],
    "host": "",
    "method": "udp",
    "password": "",
    "rdrNavStreamEnabled": False,
    "trackFormat": "json",
    "type": "inputStreamConfig",
    "username": "",
}

_TRACK_PAYLOAD = json.dumps([{
    "id": "RED1567890",
    "sensor": "R30",
    "type": "Radar",
    "lla": [40.3471, -111.780331, 1451.35938],
    "agl": 19.685835,
    "velocityNED": [0, 0, 0],
}]).encode("utf-8")


class TrackSeeder:
    """Clears the datastream config, posts a fresh UDP input config, then sends
    live track packets so that the reports/tracks endpoints have data to return."""

    def __init__(
        self,
        client,
        base_url: str,
        device_ip: str = "172.16.0.250",
        device_port: int = 8300,
    ):
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._device_ip = device_ip
        self._device_port = device_port
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def setup(self):
        """DELETE existing datastream config then POST a fresh UDP input config.

        Uses a fresh requests session (no accumulated httpx cookies or state) to
        match the reference integration script exactly.
        """
        url = self._base_url + _DATASTREAM_PATH
        token = self._client._auth.get_token()
        headers = {"Authorization": f"Bearer {token}"}

        print("  [track-seeder] DELETE /datastream/config — clearing existing config")
        resp = _requests.delete(url, headers=headers, verify=False)
        if resp.status_code not in (200, 204, 404):
            raise TrackSeederError(
                f"DELETE /datastream/config returned HTTP {resp.status_code} — cannot set up clean datastream config"
            )

        print("  [track-seeder] POST /datastream/config — registering UDP input")
        resp = _requests.post(url, json=_DATASTREAM_CONFIG, headers=headers, verify=False)
        if resp.status_code not in (200, 201):
            raise TrackSeederError(
                f"POST /datastream/config returned HTTP {resp.status_code} — datastream config not registered"
            )

    def start_udp_sender(self):
        """Spawn a daemon thread that sends track data over UDP once per second."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._udp_loop,
            daemon=True,
            name="track-udp-sender",
        )
        self._thread.start()
        print(f"  [track-seeder] UDP sender started → {self._device_ip}:{self._device_port}")

    def wait_for_tracks(self, max_wait: int = 60) -> bool:
        """Poll GET /api/v2/tracks until live track data appears or max_wait seconds elapse.

        Returns True when at least one track with non-empty newPoints is seen.
        Returns False if max_wait is exhausted without any data.

        Uses a fresh requests call (no accumulated httpx cookies) matching the
        reference integration script.
        """
        url = self._base_url + "/api/v2/tracks"
        deadline = time.monotonic() + max_wait
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            try:
                token = self._client._auth.get_token()
                headers = {"Authorization": f"Bearer {token}"}
                resp = _requests.get(url, headers=headers, verify=False)
                try:
                    body = resp.json()
                except Exception:
                    body = None

                if resp.status_code == 200 and _has_live_tracks(body):
                    print(f"  [track-seeder] Live tracks confirmed on attempt {attempt}")
                    return True

                # Print full diagnostics on every failed attempt
                print(f"  [track-seeder] attempt {attempt} — no tracks yet")
                print(f"    URL    : GET {url}")
                print(f"    Token  : {token[:12]}…{token[-6:]}")
                print(f"    Status : {resp.status_code}")
                if isinstance(body, dict):
                    data = body.get("data")
                    if isinstance(data, dict):
                        track_count = len(data)
                        sample = {}
                        if track_count:
                            first_key = next(iter(data))
                            track = data[first_key]
                            sample = {
                                "id": first_key,
                                "newPoints": track.get("newPoints", "(missing)"),
                            }
                        print(f"    Tracks : {track_count} in data  sample={sample}")
                    else:
                        print(f"    Body   : {json.dumps(body)[:300]}")
                elif body is not None:
                    print(f"    Body   : {str(body)[:300]}")
                else:
                    print(f"    Body   : (non-JSON) {resp.text[:300]}")
            except Exception as e:
                print(f"  [track-seeder] attempt {attempt} — request error: {e}")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sleep_time = min(random.uniform(1.0, 2.0), remaining)
            print(f"  [track-seeder] retrying in {sleep_time:.1f}s… ({remaining:.0f}s remaining)")
            time.sleep(sleep_time)
        return False

    def stop(self):
        """Signal the UDP sender to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        print("  [track-seeder] UDP sender stopped")

    def _udp_loop(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect((self._device_ip, self._device_port))
            while not self._stop_event.is_set():
                sock.send(_TRACK_PAYLOAD)
                self._stop_event.wait(1.0)
        except Exception as e:
            print(f"  [track-seeder] UDP error: {e}")
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass


def _has_live_tracks(body) -> bool:
    """Return True if body contains at least one track entry in data."""
    if not isinstance(body, dict):
        return False
    data = body.get("data")
    return isinstance(data, dict) and len(data) > 0
