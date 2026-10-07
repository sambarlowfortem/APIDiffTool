"""Set up a live UDP track stream so reports/tracks endpoints return real data."""

import json
import socket
import threading
import time


_DATASTREAM_PATH = "/datastream/config"

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
        """DELETE existing datastream config then POST a fresh UDP input config."""
        url = self._base_url + _DATASTREAM_PATH
        print("  [track-seeder] DELETE /datastream/config — clearing existing config")
        self._client.request("DELETE", url)
        print("  [track-seeder] POST /datastream/config — registering UDP input")
        self._client.request("POST", url, json=_DATASTREAM_CONFIG)

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
