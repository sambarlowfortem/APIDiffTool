#!/usr/bin/env python3
"""
Radio simulator for SkyDome Ground Control.

Mimics a Microhard pDDL1800-AES256 radio so SkyDome's Ground Control service
sees a connected radio without physical hardware present.

Usage:
    # Step 1 — claim the radio's IP using a macvlan with Microhard OUI (00:0f:92)
    #          The GC service checks the MAC OUI to identify Microhard hardware.
    sudo ip link add macvlan0 link enp225s0 type macvlan mode bridge
    sudo ip link set macvlan0 address 00:0f:92:aa:bb:cc
    sudo ip link set macvlan0 up
    sudo ip addr add 172.16.10.10/12 dev macvlan0
    sudo arping -c 5 -A -I macvlan0 172.16.10.10

    # Step 2 — discover what the GC service sends to the radio:
    sudo python3 radio_sim/sim.py --mode discover --no-skydome

    # Step 3 — open http://skydome.fortem:8083/details in a browser, log in,
    #           select "microhard" model, enter 172.16.10.10, click Register.
    #           Watch the discover output for what paths the GC service calls.

    # Step 4 — serve full Microhard-compatible responses (after discover):
    sudo python3 radio_sim/sim.py --mode serve --no-skydome

    # With SkyDome registration (handles the registration call for you):
    sudo python3 radio_sim/sim.py --mode serve --creds config.json

    # Remove macvlan when done:
    sudo ip link del macvlan0

Port 80 requires root (sudo). Alternative with iptables redirect:
    sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8080
Then set listen_port to 8080 in radio_sim/config.json.
"""

import argparse
import base64
import json
import os
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return json.load(f)


def merge_creds(config: dict, creds_path: str) -> dict:
    """Overlay credentials from a separate creds file (SkyDome config.json format)."""
    if creds_path and os.path.exists(creds_path):
        with open(creds_path) as f:
            creds = json.load(f)
        for key in ("sd_url", "email", "password"):
            if key in creds:
                config[key] = creds[key]
    return config


def register_radio(config: dict, auth: AuthManager) -> bool:
    """Tell SkyDome about our simulated radio via set-registered-radio."""
    import httpx
    radio = config["radio"]
    token = auth.get_token()
    url = f"{config['sd_url']}/api/v2/dronehunters/groundcontrol/set-registered-radio"
    payload = {"model": radio["model"], "address": radio["address"]}
    try:
        r = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            verify=False,
            timeout=15,
        )
        print(f"[register] set-registered-radio → HTTP {r.status_code}")
        if r.status_code >= 400:
            print(f"[register] response body: {r.text[:400]}")
            return False
        return True
    except Exception as e:
        print(f"[register] ERROR: {e}")
        return False


def verify_registration(config: dict, auth: AuthManager):
    """GET radio-frequency-settings and print the result."""
    import httpx
    token = auth.get_token()
    url = f"{config['sd_url']}/api/v2/dronehunters/groundcontrol/radio-frequency-settings"
    try:
        r = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            verify=False,
            timeout=15,
        )
        data = r.json()
        print(f"[verify] radio-frequency-settings → HTTP {r.status_code}")
        print(f"[verify] data entries: {len(data.get('data', []))}")
        if data.get("data"):
            print(f"[verify] first entry: {json.dumps(data['data'][0], indent=2)}")
        else:
            print("[verify] data is empty — radio not yet visible via API")
    except Exception as e:
        print(f"[verify] ERROR: {e}")


# ─── HTTP server handlers ─────────────────────────────────────────────────────

def _check_basic_auth(handler, radio_user: str, radio_pass: str) -> bool:
    """Return True if request carries valid Basic Auth or no auth header."""
    auth_header = handler.headers.get("Authorization", "")
    if not auth_header:
        return False  # no auth provided
    if not auth_header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        user, _, pwd = decoded.partition(":")
        return user == radio_user and pwd == radio_pass
    except Exception:
        return False


class DiscoverHandler(BaseHTTPRequestHandler):
    """Logs every request the GC service makes and returns 200 {}."""

    radio_user: str = "admin"
    radio_pass: str = "pDDL1800"
    require_auth: bool = False

    def log_message(self, fmt, *args):
        pass  # suppress default access log; we do our own

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        ts = time.strftime("%H:%M:%S")
        client_ip = self.client_address[0]

        auth_header = self.headers.get("Authorization", "(none)")
        print(f"[{ts}] DISCOVER  {self.command} {self.path}  from={client_ip}")
        print(f"         Auth:    {auth_header}")
        print(f"         Headers: {dict(self.headers)}")
        if body:
            print(f"         Body:    {body[:500]}")

        # If auth was sent, check it
        if auth_header != "(none)":
            auth_ok = _check_basic_auth(self, self.radio_user, self.radio_pass)
            print(f"         Auth OK: {auth_ok}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _handle


class ServeHandler(BaseHTTPRequestHandler):
    """Serves Microhard-compatible responses based on discovered endpoints."""

    # Injected by the server factory
    radio_config: dict = {}
    radio_user: str = "admin"
    radio_pass: str = "pDDL1800"

    def log_message(self, fmt, *args):
        pass

    def _require_auth(self) -> bool:
        """Send 401 if auth is missing or wrong. Returns True if request should proceed."""
        if _check_basic_auth(self, self.radio_user, self.radio_pass):
            return True
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] SERVE {self.command} {self.path} → 401 (auth required)")
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="UserDevice"')
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>401 Unauthorized</body></html>")
        return False

    def _json_response(self, data: dict | list, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html: str, status: int = 200):
        body = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _radio_status(self) -> dict:
        r = self.radio_config
        return {
            "address":                    r.get("address", ""),
            "bandwidth_bytes_in":         r.get("bandwidth_bytes_in", -1),
            "bandwidth_bytes_out":        r.get("bandwidth_bytes_out", -1),
            "baud_rate":                  r.get("baud_rate", 0),
            "can_frequency_hop":          r.get("can_frequency_hop", False),
            "can_set_frequency":          r.get("can_set_frequency", False),
            "can_toggle_pairing":         r.get("can_toggle_pairing", True),
            "can_toggle_transmit":        r.get("can_toggle_transmit", True),
            "frequency":                  r.get("frequency", 1820),
            "frequency_hop_threshold_db": r.get("frequency_hop_threshold_db"),
            "frequency_ranges":           r.get("frequency_ranges", []),
            "hop_frequencies":            r.get("hop_frequencies", []),
            "id":                         r.get("address", ""),
            "is_frequency_hop_enabled":   r.get("is_frequency_hop_enabled", False),
            "is_network_id_number":       r.get("is_network_id_number", False),
            "make":                       r.get("make", "Microhard"),
            "model":                      r.get("model", "pDDL1800-AES256"),
            "network_id":                 r.get("network_id", ""),
            "network_id_range":           r.get("network_id_range"),
            "serial_port_path":           r.get("serial_port_path"),
            "transmitting":               r.get("transmitting", True),
            "type":                       r.get("type", "UDP"),
        }

    def _cgi_status_csv(self) -> str:
        """Return a Microhard-style CSV status string (for web UI compatibility)."""
        r = self.radio_config
        freq = r.get("frequency", 1820)
        network_id = r.get("network_id", "")
        tx = "1" if r.get("transmitting", True) else "0"
        # Minimal CSV format matching Microhard getradio.sh output
        return f"0KB,0,0KB,0,0,{tx},{freq},{network_id}"

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        ts = time.strftime("%H:%M:%S")
        auth_header = self.headers.get("Authorization", "(none)")
        print(f"[{ts}] SERVE GET {path}  auth={auth_header[:40]}")

        status = self._radio_status()

        # Root redirect (matching real Microhard behaviour)
        if path == "/":
            self.send_response(301)
            self.send_header("Location", "/cgi-bin/webif/system-info.sh")
            self.end_headers()
            return

        # CGI status endpoints — these need auth on the real device
        if path in ("/cgi-bin/webif/system-info.sh",
                    "/cgi-bin/webif/status.sh",
                    "/cgi-bin/webif/radioinfo.sh",
                    "/cgi-bin/webif/radio-status.sh"):
            if not self._require_auth():
                return
            # Return a minimal HTML status page matching real device
            freq = self.radio_config.get("frequency", 1820)
            net_id = self.radio_config.get("network_id", "")
            tx = self.radio_config.get("transmitting", True)
            html = (
                f"<html><body>"
                f"<p>Frequency: {freq} MHz</p>"
                f"<p>Network ID: {net_id}</p>"
                f"<p>Transmit: {'on' if tx else 'off'}</p>"
                f"</body></html>"
            )
            self._html_response(html)
            return

        # Radio status CGI — used by Microhard web UI JS
        if path == "/cgi-bin/webif/getradio.sh":
            if not self._require_auth():
                return
            body = self._cgi_status_csv().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # JSON status endpoints — serve radio data regardless of auth
        # (GC service may call these without auth or with auth we honour above)
        if path in ("/status", "/api/status", "/radio/status",
                    "/api/radio", "/api/radio/status",
                    "/api/v1/status", "/api/v1/radio",
                    "/cgi-bin/sts.cgi", "/cgi-bin/status.cgi"):
            self._json_response(status)
            return

        if path in ("/config", "/api/config", "/radio/config",
                    "/cgi-bin/cfg.cgi", "/api/v1/config"):
            self._json_response(status)
            return

        if path in ("/frequency", "/api/frequency", "/radio/frequency"):
            self._json_response({
                "frequency": status["frequency"],
                "transmitting": status["transmitting"],
                "network_id": status["network_id"],
            })
            return

        # Unknown path — log and return full status anyway (for discovery)
        print(f"         (UNKNOWN PATH — returning full status as discovery fallback)")
        self._json_response(status)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        ts = time.strftime("%H:%M:%S")
        auth_header = self.headers.get("Authorization", "(none)")
        print(f"[{ts}] SERVE POST {self.path}  auth={auth_header[:40]}  body={body[:200]!r}")
        self._json_response({"success": True})

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] SERVE PUT {self.path}  body={body[:200]!r}")
        self._json_response({"success": True})

    do_PATCH = do_PUT
    do_DELETE = do_PUT

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Allow", "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS")
        self.end_headers()


def make_serve_handler(radio_config: dict, radio_user: str = "admin", radio_pass: str = "pDDL1800"):
    """Return a ServeHandler subclass with config and credentials injected."""
    class Handler(ServeHandler):
        pass
    Handler.radio_config = radio_config
    Handler.radio_user = radio_user
    Handler.radio_pass = radio_pass
    return Handler


def make_discover_handler(radio_user: str = "admin", radio_pass: str = "pDDL1800"):
    class Handler(DiscoverHandler):
        pass
    Handler.radio_user = radio_user
    Handler.radio_pass = radio_pass
    return Handler


def start_server_thread(host: str, port: int, handler_class) -> HTTPServer:
    """Start an HTTPServer in a background thread and return it."""
    server = HTTPServer((host, port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def start_raw_tcp_listener(host: str, port: int, radio_user: str = "admin", radio_pass: str = "pDDL1800", radio_config: dict = None):
    """Start a raw TCP listener that mimics a Telnet login to capture the full GC service exchange."""
    def _accept_loop(srv_sock):
        while True:
            try:
                conn, addr = srv_sock.accept()
            except OSError:
                break
            threading.Thread(target=_handle_telnet, args=(conn, addr), daemon=True).start()

    def _recv_line(conn, timeout=8) -> bytes:
        """Read until newline or timeout."""
        conn.settimeout(timeout)
        buf = b""
        try:
            while True:
                ch = conn.recv(1)
                if not ch:
                    break
                buf += ch
                if ch in (b"\n", b"\r"):
                    # consume trailing \n after \r
                    try:
                        conn.settimeout(0.2)
                        extra = conn.recv(1)
                        if extra not in (b"\n", b""):
                            buf += extra
                    except Exception:
                        pass
                    break
        except Exception:
            pass
        return buf

    def _radio_json() -> bytes:
        r = radio_config if radio_config else {}
        payload = {
            "address":                    r.get("address", ""),
            "bandwidth_bytes_in":         r.get("bandwidth_bytes_in", -1),
            "bandwidth_bytes_out":        r.get("bandwidth_bytes_out", -1),
            "baud_rate":                  r.get("baud_rate", 0),
            "can_frequency_hop":          r.get("can_frequency_hop", False),
            "can_set_frequency":          r.get("can_set_frequency", False),
            "can_toggle_pairing":         r.get("can_toggle_pairing", True),
            "can_toggle_transmit":        r.get("can_toggle_transmit", True),
            "frequency":                  r.get("frequency", 1820),
            "frequency_hop_threshold_db": r.get("frequency_hop_threshold_db"),
            "frequency_ranges":           r.get("frequency_ranges", []),
            "hop_frequencies":            r.get("hop_frequencies", []),
            "id":                         r.get("address", ""),
            "is_frequency_hop_enabled":   r.get("is_frequency_hop_enabled", False),
            "is_network_id_number":       r.get("is_network_id_number", False),
            "make":                       r.get("make", "Microhard"),
            "model":                      r.get("model", "pDDL1800-AES256"),
            "network_id":                 r.get("network_id", ""),
            "network_id_range":           r.get("network_id_range"),
            "serial_port_path":           r.get("serial_port_path"),
            "transmitting":               r.get("transmitting", True),
            "type":                       r.get("type", "UDP"),
        }
        return (json.dumps(payload) + "\n").encode()

    # Telnet negotiation bytes the real Microhard sends on connect
    # IAC WILL ECHO, IAC WILL SGA, IAC DO NAWS  (typical embedded device set)
    TELNET_BANNER = (
        b"\xff\xfb\x01"   # IAC WILL ECHO
        b"\xff\xfb\x03"   # IAC WILL SGA
        b"\xff\xfd\x1f"   # IAC DO NAWS
        b"\r\n\r\nUserDevice login: "
    )

    def _read_until_nl(conn, timeout=8) -> bytes:
        """Read bytes until CR or LF, return stripped content."""
        conn.settimeout(timeout)
        buf = b""
        try:
            while True:
                ch = conn.recv(1)
                if not ch:
                    break
                # Skip Telnet IAC negotiation bytes (IAC cmd opt = 3 bytes)
                if ch == b"\xff":
                    conn.recv(2)
                    continue
                if ch == b"\r":
                    # Consume trailing \n of CRLF only
                    try:
                        conn.settimeout(0.05)
                        nxt = conn.recv(1)
                        if nxt not in (b"\n", b""):
                            buf += nxt  # not \n, put it back conceptually — log it
                    except Exception:
                        pass
                    break
                if ch == b"\n":
                    break  # standalone LF — don't drain anything
                buf += ch
        except Exception:
            pass
        return buf

    def _handle_telnet(conn, addr):
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] TELNET  from={addr[0]}:{addr[1]}")
        try:
            # Send Telnet banner matching real Microhard device
            conn.sendall(TELNET_BANNER)

            # Read username
            user_in = _read_until_nl(conn).decode("utf-8", errors="replace")
            print(f"         username: {user_in!r}")

            # Send password prompt
            conn.sendall(b"Password: ")

            # Read password
            pass_in = _read_until_nl(conn).decode("utf-8", errors="replace")
            print(f"         password: {pass_in!r}")

            auth_ok = (user_in == radio_user and pass_in == radio_pass)
            print(f"         auth OK: {auth_ok}")

            # Send shell prompt
            conn.sendall(b"\r\n\r\n# ")

            # Read commands until connection closes
            r = radio_config or {}
            model = r.get("model", "pDDL1800-AES256")

            while True:
                cmd = _read_until_nl(conn, timeout=10)
                if not cmd:
                    break
                cmd_str = cmd.decode("utf-8", errors="replace")
                print(f"         command: {cmd_str!r}")

                # Only respond with JSON if the command matches our model.
                # The real radio only has a command for its own model and returns
                # "not found" for all other model commands.
                if cmd_str and model.startswith(cmd_str):
                    # Send JSON + shell prompt as one block (matches real radio byte sequence)
                    print(f"         → matched model, sending JSON")
                    conn.sendall(_radio_json() + b"\r\n# ")
                else:
                    # Shell "command not found" — same as a real non-matching radio
                    conn.sendall(f"\r\n-sh: {cmd_str}: not found\r\n# ".encode())

        except Exception as e:
            print(f"         session ended: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(10)
    t = threading.Thread(target=_accept_loop, args=(srv,), daemon=True)
    t.start()
    print(f"[sim] Telnet listener on {host}:{port}")
    return srv


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SkyDome radio simulator")
    parser.add_argument("--mode", choices=["discover", "serve"], default="discover",
                        help="discover: log all GC requests; serve: full Microhard responses")
    parser.add_argument("--config", default=os.path.join(_HERE, "config.json"),
                        help="Path to radio_sim/config.json")
    parser.add_argument("--creds", default=None,
                        help="Path to SkyDome credentials file (config.json format). "
                             "Overrides sd_url/email/password in --config.")
    parser.add_argument("--no-register", action="store_true",
                        help="Skip registering the radio with SkyDome")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip verification GET after registration")
    parser.add_argument("--no-skydome", action="store_true",
                        help="Skip all SkyDome API calls (no auth, no register, no verify). "
                             "Useful when just running the listener for discovery.")
    parser.add_argument("--extra-ports", default="",
                        help="Comma-separated list of additional ports to listen on "
                             "(e.g. 8080,8443,9090). Useful if GC service uses a non-80 port.")
    parser.add_argument("--telnet", action="store_true",
                        help="Also listen on port 23 with a raw TCP sniffer "
                             "(captures any Telnet/CLI connection the GC service might make)")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.creds:
        config = merge_creds(config, args.creds)

    radio = config.get("radio", {})
    listen_host = config.get("listen_host", "0.0.0.0")
    listen_port = int(config.get("listen_port", 80))
    radio_user = config.get("radio_http_user", "admin")
    radio_pass = config.get("radio_http_pass", "pDDL1800")

    extra_ports = []
    if args.extra_ports:
        for p in args.extra_ports.split(","):
            p = p.strip()
            if p.isdigit():
                extra_ports.append(int(p))

    print(f"[sim] mode={args.mode}  radio={radio.get('model','?')} @ {radio.get('address','?')}")
    print(f"[sim] server={listen_host}:{listen_port}")
    if extra_ports:
        print(f"[sim] extra ports: {extra_ports}")

    auth = None
    if not args.no_skydome:
        import sys as _sys
        _sys.path.insert(0, _ROOT)
        from probe.auth import AuthManager
        import httpx  # noqa: F401 — ensure available for register/verify
        sd_url = config.get("sd_url", "")
        email = config.get("email", "")
        password = config.get("password", "")
        if not email or not password:
            print("ERROR: email and password must be set in config (or --creds file), "
                  "or use --no-skydome to skip SkyDome API calls")
            sys.exit(1)
        print(f"[sim] skydome={sd_url}")
        auth = AuthManager(sd_url, email, password)
        print("[sim] Authenticating with SkyDome...")
        auth.login()
        auth.start_auto_refresh()
        print("[sim] Auth OK")

    if not args.no_skydome and not args.no_register:
        if radio.get("address") in ("", "CHANGE_TO_TEST_MACHINE_IP"):
            print("ERROR: set radio.address in config to this machine's IP address")
            sys.exit(1)
        print("[sim] Registering radio with SkyDome...")
        ok = register_radio(config, auth)
        if not ok:
            print("[sim] WARNING: registration failed — server will still start")

    if not args.no_skydome and not args.no_verify:
        time.sleep(1)
        verify_registration(config, auth)

    # Build handler
    if args.mode == "discover":
        handler = make_discover_handler(radio_user, radio_pass)
    else:
        handler = make_serve_handler(radio, radio_user, radio_pass)

    # Start primary server
    server = start_server_thread(listen_host, listen_port, handler)

    # Start extra port servers
    extra_servers = []
    for p in extra_ports:
        try:
            s = start_server_thread(listen_host, p, handler)
            extra_servers.append(s)
            print(f"[sim] Also listening on {listen_host}:{p}")
        except Exception as e:
            print(f"[sim] WARNING: could not bind port {p}: {e}")

    # Start Telnet raw listener if requested
    if args.telnet:
        try:
            start_raw_tcp_listener(listen_host, 23, radio_user, radio_pass, radio)
        except Exception as e:
            print(f"[sim] WARNING: could not bind port 23: {e}")

    def _shutdown(sig, frame):
        print("\n[sim] Shutting down...")
        for s in [server] + extra_servers:
            threading.Thread(target=s.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    mode_label = "DISCOVER (logging all requests)" if args.mode == "discover" else "SERVE (Microhard responses)"
    print(f"[sim] Server running on {listen_host}:{listen_port} [{mode_label}]")
    print(f"[sim] Ctrl+C to stop")
    server.serve_forever()


if __name__ == "__main__":
    main()
