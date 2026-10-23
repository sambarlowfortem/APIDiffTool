# Radio Simulator Investigation

## Goal

Convince SkyDome's Ground Control (GC) service that a Microhard pDDL1800-AES256 radio is
connected when no physical hardware is present, so that:

- `GET /api/v2/dronehunters/groundcontrol/radio-frequency-settings` returns populated data
- `http://skydome.fortem:8083/details` shows the radio in the "radios connected" section

---

## System Architecture

```
SkyDome Manager (HTTPS :443)     ←→  probe/viewer tooling
Ground Control service (HTTP :8083)  ←→  browser UI (ws/radios WebSocket)
                        ↕
              Microhard radio (Telnet :23)
```

The GC service is a separate Java process at `http://skydome.fortem:8083`.
It authenticates via `api_key` header.  The SkyDome Manager proxies some GC endpoints
(e.g. `set-registered-radio`, `radio-frequency-settings`) under `/api/v2/dronehunters/groundcontrol/`.

**GC API key** (from `GET /api/v2/dronehunters/groundcontrol`):
`lima-0D8j6u^9Pz#1e3!y*pp9!0i#Myu9f`

**Radio data feed:** the GC pushes radio state over WebSocket at `ws://skydome.fortem:8083/ws/radios`.
The browser's Details page subscribes to this feed. The SkyDome Manager's
`radio-frequency-settings` endpoint reads from the same source.

---

## How the GC Service Talks to the Radio

The GC service does **not** use HTTP to poll the radio. It uses **Telnet (port 23)**.

### Discovery: what we observed

- The GC service opens a new TCP connection to 172.16.10.10:23 approximately every 7 seconds.
- Each connection authenticates and sends exactly **one model command**, cycling through all known
  Microhard models in order: `pDDL900`, `pMDDL1624`, `pDDL1800`, `pMDDL2450`, `pMDDL2450JP`.
- Full cycle = ~35 seconds.
- This is the **discovery** mode — the GC is trying all model-specific shell commands to find out
  which Microhard model is present.

### Telnet exchange (byte-level)

```
Server → Client  (our simulator sends):
  FF FB 01          IAC WILL ECHO
  FF FB 03          IAC WILL SGA
  FF FD 1F          IAC DO NAWS
  \r\n\r\n
  UserDevice login: 

Client → Server  (GC service sends):
  \r\n              (blank username — CRLF)

Server → Client:
  Password: 

Client → Server:
  admin\r\n

Server → Client:
  \r\n\r\n# 

Client → Server:
  pDDL1800\r\n      (or whichever model is being tried this cycle)

Server → Client  (if model matches):
  {"address":"172.16.10.10","bandwidth_bytes_in":-1,...}\n\r\n# 

Server → Client  (if model does NOT match):
  \r\n-sh: pDDL900: not found\r\n# 
```

Key detail: the real radio sends the JSON blob and the shell prompt **in one TCP segment**
(`{...}\n\r\n# `). Our simulator now does the same via a single `conn.sendall()` call.

### The JSON payload

The `pDDL1800` command returns a flat JSON object. The real radio's response
(captured from the live system via a direct Python Telnet session) is:

```json
{
  "address": "172.16.10.10",
  "bandwidth_bytes_in": -1,
  "bandwidth_bytes_out": -1,
  "baud_rate": 0,
  "can_frequency_hop": false,
  "can_set_frequency": false,
  "can_toggle_pairing": true,
  "can_toggle_transmit": true,
  "frequency": 1820,
  "frequency_hop_threshold_db": null,
  "frequency_ranges": [],
  "hop_frequencies": [],
  "id": "172.16.10.10",
  "is_frequency_hop_enabled": false,
  "is_network_id_number": false,
  "make": "Microhard",
  "model": "pDDL1800-AES256",
  "network_id": "FTxDH",
  "network_id_range": null,
  "serial_port_path": null,
  "transmitting": true,
  "type": "UDP"
}
```

The simulator's `_radio_json()` function generates an identical payload (same keys, same order,
same types) from `radio_sim/config.json`.

### How ws/radios is populated

Observed via WebSocket when the real radio was plugged in:

1. **First broadcast** (within ~2 minutes of plugging in):
   `[{..., "frequency": null, "model": "pDDL1800-AES256", ...}]`
2. **Second broadcast** (1 second later):
   `[{..., "frequency": 1820.0, "model": "pDDL1800-AES256", ...}]`

The GC creates an **incomplete entry** (frequency=null) from something other than the Telnet
probe, then fills in the frequency from the Telnet probe result. This two-phase behavior means
there is a separate "initial detection" step before Telnet.

---

## What the Simulator Does

`radio_sim/sim.py` with `--mode discover --no-skydome --telnet`:

1. Listens on `0.0.0.0:23` for Telnet connections.
2. Sends the exact Telnet banner (`IAC WILL ECHO / WILL SGA / DO NAWS`) that the real
   Microhard sends.
3. Reads the blank username and `admin` password.
4. Sends the shell prompt `\r\n\r\n# `.
5. Reads commands in a loop.
6. For `pDDL1800` (or any prefix of `pDDL1800-AES256`): sends the full JSON blob + `\r\n# `
   in one `sendall` call.
7. For all other Microhard model commands: sends `-sh: <cmd>: not found\r\n# ` (same as a
   real pDDL1800 responding to a command it doesn't have).

The exchange itself is verified correct — the GC service connects, goes through the full login
sequence, and receives the JSON for `pDDL1800`. This was confirmed by both:
- Watching the simulator's log output showing `→ matched model, sending JSON`
- Running `printf "\r\nadmin\r\npDDL1800\r\n" | nc -q 2 172.16.10.10 23` and seeing
  identical JSON to the real radio's response.

---

## The Blocker

Despite the correct Telnet exchange, `ws/radios` stays `[]` and the radio never appears.

### Most likely explanation: MAC OUI check during initial detection

The real Microhard radio's MAC address: `00:0f:92:0c:cc:e8`
OUI `00:0f:92` = Microhard Communications Inc.

The original IP alias used the laptop NIC's MAC: `9c:6b:00:d6:cc:a6` (not a Microhard OUI).

**Hypothesis:** the GC service's "initial detection" step (the one that creates the incomplete
entry) checks the MAC OUI of the device at 172.16.10.10. If the OUI matches Microhard, it
creates the entry; the subsequent Telnet probe then fills in the details. With a non-Microhard
MAC, the GC still probes via Telnet (it has 172.16.10.10 in its configured probe list) but the
probe results have nowhere to be stored.

### What was tried to fix it

A `macvlan` interface was created to allow setting a Microhard OUI MAC:

```bash
sudo ip link add macvlan0 link enp225s0 type macvlan mode bridge
sudo ip link set macvlan0 address 00:0f:92:aa:bb:cc
sudo ip link set macvlan0 up
sudo ip addr add 172.16.10.10/12 dev macvlan0
ping -c 3 -I macvlan0 172.16.0.250   # populate GC's ARP cache
```

This did not resolve the issue. The radio still did not appear after several minutes.

### Why we couldn't go further

The GC service's registration state machine is opaque. Without either:
- tcpdump on the GC server (172.16.0.250) to compare traffic when the real radio connects
  vs when the simulator runs
- Access to the GC service's source code or application logs

...it is not possible to determine what additional check is failing. Candidates beyond MAC OUI:

- The GC stores the **specific MAC** (not just OUI) from a previous registration, and the
  `aa:bb:cc` suffix doesn't match `0c:cc:e8`.
- There is an **HTTP probe** on port 80 that must succeed before Telnet results are accepted.
  (Note: during earlier discover-mode HTTP logging, the GC service never connected to port 80
  on the simulator — but that was with a non-Microhard MAC. With a Microhard MAC, the GC
  might try HTTP first.)
- The GC's "initial detection" uses a **separate scan interval** (~2 minutes) and the ARP
  announcement hasn't been picked up yet.
- There is a **hardware fingerprint** check (TCP window size, TTL, OS fingerprint) beyond MAC.

---

## Current State of the Code

`radio_sim/sim.py` is functional and correct at the protocol level. To run:

```bash
# Set up the network interface (Microhard OUI)
sudo ip link add macvlan0 link enp225s0 type macvlan mode bridge
sudo ip link set macvlan0 address 00:0f:92:aa:bb:cc
sudo ip link set macvlan0 up
sudo ip addr add 172.16.10.10/12 dev macvlan0
ping -c 3 -I macvlan0 172.16.0.250

# Run the simulator
sudo python3 -u radio_sim/sim.py --mode discover --no-skydome --telnet

# Teardown
sudo ip link del macvlan0
```

`radio_sim/config.json` contains the pre-populated radio fields matching the live capture.

---

## If Returning to This

The fastest path to a resolution would be:

1. **Run tcpdump on the GC server** while plugging in the real radio, and separately while
   the simulator is running. Compare what traffic the GC generates in each case (especially
   any non-Telnet traffic to 172.16.10.10).

   ```bash
   # On 172.16.0.250 (requires SSH access to the SkyDome host)
   sudo tcpdump -i any host 172.16.10.10 -w /tmp/radio_capture.pcap
   ```

2. **Check GC service logs** on 172.16.0.250 — the Java process will likely log the
   reason it rejects the Telnet response or fails to create the radio entry.

3. **Try HTTP on port 80** with a Microhard OUI MAC active — run the simulator in
   `--mode serve` alongside `--telnet` to serve the CGI-style HTTP endpoints that a real
   Microhard would have. The GC might require a successful HTTP probe before accepting
   Telnet data.

4. **Use `arping -U`** (gratuitous ARP) rather than ping to announce the macvlan. Some
   switches and hosts respond better to unsolicited ARP announcements. Install with
   `sudo apt install iputils-arping`.
