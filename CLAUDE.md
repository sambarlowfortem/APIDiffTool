# API Diff Tool

A black-box API prober and diff viewer for the SkyDome Smart API. Built to record everything observable about one API version into a structured JSON snapshot, and compare any two snapshots by structure and type — never by value.

## What this tool does

**Component 1 — Prober** (`probe/probe.py`): Authenticates against a running SkyDome instance, sends all 7 HTTP methods to every registered endpoint, performs field ablation on writable endpoints to empirically determine which fields are required, infers response field types and formats, and runs the whole sweep under three Docker container scenarios. Outputs a JSON snapshot and an HTML run report.

**Component 2 — Diff viewer** (`viewer/index.html`): A single self-contained HTML file. Point it at a `results/` folder, pick two runs from any two versions, and see every change in endpoints, required fields, response fields, types, formats, and deprecations. No server, no install, no build step.

The contract between them is documented in `SCHEMA.md`.

## Running the prober

```bash
# Full run (all three container scenarios)
python3 probe/probe.py --version 5.2.3 --base-url https://skydome.fortem --out results/

# Single-scenario run (current container state, no docker management)
python3 probe/probe.py --version 5.2.3 --base-url https://skydome.fortem --out results/ --skip-containers

# With request throttling (recommended: 0.1s between requests)
python3 probe/probe.py --version 5.2.3 --base-url https://skydome.fortem --out results/ --delay 0.1

# Mask sensitive fields in the HTML report
python3 probe/probe.py --version 5.2.3 --out results/ --redact password,apiKey,token
```

Credentials are read from `config.json` in the working directory:
```json
{"sd_url": "https://skydome.fortem", "email": "...", "password": "..."}
```

Output lands in `results/<version>/<run_id>.json` and `results/<version>/<run_id>.report.html`.

## Using the diff viewer

Open `viewer/index.html` in a browser. Click "Choose results folder" and select the `results/` directory. All version subdirectories are read recursively. Pick a version on each side — the diff runs automatically. Use `fixtures/results/` to test the viewer against hand-crafted fixtures without running the prober.

Runs in `results/_archive/` are ignored by the viewer. Move unwanted runs there to hide them without deleting them.

## Project layout

```
SCHEMA.md               Contract between the two components — read this first
endpoints.yaml          Registry of all known API endpoints (registry_version: 2)
endpoints_schema.json   JSON Schema used to validate endpoints.yaml at probe time
probe/
  probe.py              CLI entrypoint
  auth.py               Login + auto-refresh (55 min background thread)
  registry.py           YAML loader, JSON Schema validation, ParamResolver
  baseline.py           Not-found signature recorder
  http_client.py        httpx wrapper — retries, 429 handling, per-request delay
  matrix.py             All 7 methods × every endpoint
  ablation.py           Field-by-field required/optional discovery
  formats.py            40 format detectors (FORMAT_DETECTORS_VERSION = "1.0")
  schema_utils.py       genson-based schema inference, dot-notation flattening
  containers.py         Docker SDK scenario management
  report.py             Jinja2 HTML run report
  templates/
    report.html.j2      Self-contained run report template
  test_formats.py       55 format detector assertions (run with python3 probe/test_formats.py)
viewer/
  index.html            Complete diff viewer — single file, no dependencies
fixtures/
  results/              Hand-crafted fixture snapshots for viewer testing
    5.1.0/              Older version (4 variants including 3 compat fixtures)
    5.2.0/              Newer version with planted diffs (rc1 + final)
    _archive/           One archived run (ignored by viewer)
results/                Real probe output (gitignore large runs if needed)
scripts/
  parse_docs.py         One-off BeautifulSoup parser used to generate endpoints.yaml v1
```

## Target system

- **Base URL**: `https://skydome.fortem` (local server, SSL verify=False)
- **Auth**: Bearer token via `POST /api/v2/system/users/login`
- **API version probed so far**: 5.2.3 (docs: `SkyDome_Smart_API_5.2.3.html`)
- **API path prefix**: `/api/v2/` — except `/datastream/config` which sits at the root

## Docker container scenarios

The prober runs the probe matrix three times, once per container state:

| Scenario | dronehangar | dronehunter-1 | dronehunter-2 | dronehunter-3 |
|---|---|---|---|---|
| `no_containers` | stopped | stopped | stopped | stopped |
| `containers_present` | running | running | stopped | stopped |
| `multiple_hunters` | running | running | running | running |

**Rules:**
- There is at most 1 DroneHangar. Never test a multi-hangar scenario.
- `firefly-radar-sim-radar-1` stays running always. Test absent-radar scenarios by deleting the sensor via the API, not by stopping the container.
- RF sensors need no container — add and retrieve them from the API without any backing hardware.
- The prober saves the initial container state at startup and restores it on exit (try/finally).

## Registry rules

- **Never delete an entry.** When an endpoint leaves the docs, add `removed_from_docs: "<version>"` instead.
- **Bump `registry_version` on every edit.**
- `skip_methods` blocks specific HTTP methods from being sent to an endpoint. Use it for endpoints whose side effect is real and irreversible (e.g. `service/shutdown`, `service/restart`).
- `body` values that are JSON arrays (not objects) are skipped by the ablation loop with a `body_not_object_skipped_ablation` flag.

## Known dangerous endpoints

These are in the registry with `skip_methods: [POST, PUT, PATCH, DELETE]`:

- `POST /api/v2/service/shutdown` — **shuts down the SkyDome Manager**. Discovered the hard way: the prober crashed the target machine three times before this was caught.
- `POST /api/v2/service/restart` — restarts the SkyDome Manager.

The prober will send GET/HEAD/OPTIONS to these (which return 405) but skip all write methods.

## Format detectors

`probe/formats.py` implements 40 named formats (see `SCHEMA.md` section 4 for the full vocabulary). Run `python3 probe/test_formats.py` to verify all 55 assertions pass. Bump `FORMAT_DETECTORS_VERSION` in `formats.py` whenever detectors change — this is recorded in every snapshot so the diff viewer can flag format changes that may be detector-version artifacts rather than API changes.

## Snapshot schema

Schema version `"1.0"`. The `run_id` is also the filename (without `.json`). Format: `<version>__<build>__<YYYYMMDD-HHMMSS>`. Each endpoint entry has a `scenario` field — the same path+method appears once per container scenario. Component 2 only compares within matching scenario names.

## Adding a new API version

1. Compare the new docs with `endpoints.yaml`. Add new endpoints, mark removed ones with `removed_from_docs`.
2. Add `deprecated.in` for anything newly marked deprecated in the docs.
3. Bump `registry_version` and commit.
4. Deploy the new version to the test instance.
5. Run `python3 probe/probe.py --version <new_version> --out results/`.
6. Open `viewer/index.html`, load `results/`, compare.
