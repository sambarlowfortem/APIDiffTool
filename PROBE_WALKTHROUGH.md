# Probe Walkthrough

A step-by-step description of exactly what `probe/probe.py` does when you run it — every request, every ordering rule, every time gate, and every retry.

---

## 1. Startup

The prober reads credentials and the base URL from `config.json` (or the command line). It then:

1. Loads and validates `endpoints.yaml` against `endpoints_schema.json`. If the YAML is invalid, it aborts immediately.
2. Calls `POST /api/v2/system/users/login` with `{"email": "...", "password": "..."}` to get a Bearer token.
3. Starts a background thread that silently re-calls `GET /api/v2/system/users/token/refresh` every **55 minutes** so the token never expires mid-run. If the refresh fails, it falls back to a full re-login.

---

## 2. Not-found baseline

Before probing anything real, the prober needs to know what a "this endpoint doesn't exist" response looks like on this particular server, because different servers return different status codes and content-types for missing routes.

It sends `GET` and `POST` to **six made-up URLs** — two each in three URL patterns:

```
/__probe_missing_<random>
/api/v2/__probe_missing_<random>
/api/v2/some/__probe_missing_<random>
```

It records the HTTP status code and content-type from each response. If all six agree, it stores a single not-found signature. If they differ (e.g. the root returns 404 but `/api/v2/` returns 405), it stores one signature per pattern. Everything probed later is compared against this signature to decide whether an endpoint "exists."

---

## 3. Container scenarios

By default the prober runs two container scenarios in sequence: **`no_containers`** then **`containers_present`**.

### no_containers

The prober assumes the Docker containers are already stopped at startup and **skips all container management**. It goes straight to probing.

> **Strict ordering note:** `no_containers` always runs before `containers_present` because the prober relies on the containers being down at startup as a known starting point.

### containers_present

Before probing, the prober calls the Docker daemon to start `dronehangar` and `dronehunter-1`, and stop `dronehunter-2` and `dronehunter-3`.

It then **polls the API** every 2 seconds until the API reflects the right container counts:

- `GET /api/v2/dronehunters/hangars` → expects 1 item
- `GET /api/v2/dronehunters` → expects 1 item

It will keep polling for up to `--settle-wait` seconds (default **20 seconds**). If the API still doesn't agree after the timeout, it logs a warning and continues anyway.

> **Time gate:** This 20-second settle wait is a hard pause. Nothing else happens until the API reflects the new container state (or the timeout fires).

**Important:** The `containers_present` scenario only probes the DroneHunter endpoints (`/api/v2/dronehunters/...`). All other endpoints are excluded from this scenario's pass — they've already been covered in `no_containers`.

---

## 4. The probe matrix (runs once per scenario)

For each endpoint in `endpoints.yaml`, in the order they appear in the file, the prober:

### 4a. Resolve path parameters

If the endpoint URL contains a `{param}` placeholder (e.g. `/api/v2/rules/{id}`), the prober looks up the dependency defined in `endpoints.yaml` to find a real ID to use — typically by calling a collection endpoint and picking the first item's `_id`. If no real ID can be found, the endpoint is marked `param_resolution_failed` and skipped.

### 4b. Pre-create requests

Some endpoints require a resource to already exist before they can be probed (e.g. you can't test `PUT /dronehunters/geocages/{name}` if no geocage exists yet). For these, the registry defines a list of `pre_create` requests that run first, in order, before any of the four main methods are tried.

### 4c. Send requests in method order

For each method in the endpoint's probe order — default is `POST, PUT, GET, DELETE` — the prober sends one request with a Bearer token in the `Authorization` header. It records the status code and parses the JSON response body to infer a field schema.

- `POST` and `PUT` requests include the example request body from `endpoints.yaml` as JSON. `GET` and `DELETE` requests have no body.
- If an endpoint has a **`probe_order`** override in the registry, that order is used instead of the default. Any methods not mentioned in the override are appended at the end.
- If an endpoint has **`skip_methods`**, those methods are silently skipped (no request is sent at all).

**Endpoints with notable ordering or skip rules:**

| Endpoint | Rule |
|---|---|
| `/api/v2/service/restart` | Only `GET` is sent. `POST`, `PUT`, `DELETE` are all skipped (would restart the SkyDome Manager). |
| `/api/v2/service/shutdown` | Only `GET` is sent. `POST`, `PUT`, `DELETE` are all skipped (would shut down the SkyDome Manager). |
| `/api/v2/app/reset-system-setup` | `POST` is skipped. |
| `/api/v2/sensors/rfsensors/jam` | `POST` is skipped. |
| `/datastream/config` | **Custom probe order: `DELETE, GET, POST, PUT`** — DELETE runs first to verify the endpoint works cleanly before a config exists. |
| `/api/v2/sensors/cameras` | **Custom probe order: `POST, GET, PUT, DELETE`** — POST first so there's a camera resource for the GET/PUT/DELETE calls. |
| `/api/v2/sensors/radars/{id}` | `PUT` is skipped. |
| `/api/v2/sensors/cameras/{id}` | Appears **twice** in the registry. First entry skips `DELETE` (probes GET + PUT). Second entry skips `GET`, `PUT`, `POST` (probes DELETE only). This separates the read and destructive passes. |
| All `with_tracks_only` endpoints | Completely **excluded** from the `no_containers` and `containers_present` passes. They only run in the track-seeded pass (see section 5). |

### 4d. Retry logic for /api/v2/tracks (with_tracks scenario only)

In the track-seeded pass, `GET /api/v2/tracks` is retried up to **20 times** if the response is empty or returns a 429. Between each retry the prober sleeps a **random 1–2 seconds** to avoid phase-locking with the server's 1Hz data update window.

### 4e. Post-endpoint cleanup

After all four methods have been sent for an endpoint, the prober attempts a best-effort `DELETE` on any resource that was created by the `POST` probe (by extracting the `_id` from the POST response). This only applies to collection endpoints without path parameters (e.g. `POST /api/v2/zones` creates a zone, so the prober sends `DELETE /api/v2/zones/{id}` afterward). If the DELETE fails for any reason, it is silently ignored.

---

## 5. Ablation (runs immediately after each scenario's matrix)

Ablation empirically determines which request body fields are truly required by the API (as opposed to just optional). It only runs for `POST` and `PUT` requests on listed endpoints that have an example body defined and whose baseline request succeeded (status 200–299).

For each field in the example body, the prober:

1. Sends the same `POST` or `PUT` with **that one field removed**.
2. Interprets the response:
   - **200–299** → field is **optional** (server accepted the request without it)
   - **400–499** → field is **required** (server rejected the request)
   - **5xx or connection error** → field is treated as **optional** (ambiguous result)
3. Attempts a best-effort `DELETE` cleanup after each call, in case the server created a resource.

If the body is a JSON array rather than an object (can't remove named fields), ablation is skipped for that endpoint and a `body_not_object_skipped_ablation` flag is set.

---

## 6. Track-seeded pass

This pass runs after all container scenarios. It injects live track data and then re-probes the track and camera endpoints so they return real response schemas rather than empty arrays.

### 6a. Datastream setup

> **Strict ordering:** These two steps must happen in order and both must succeed or the entire track pass aborts.

1. `DELETE /datastream/config` — clears any existing datastream config. Accepts 200, 204, or 404 (already empty) as success.
2. `POST /datastream/config` — registers a new UDP input config pointing at the local test network (`172.16.0.250:8300`). Must return 200 or 201.

This uses a **fresh HTTP client** (not the shared one used for the rest of the probe) to avoid cookie accumulation issues that were causing 401 errors.

### 6b. UDP track sender

A background thread starts sending a synthetic track payload over UDP to `172.16.0.250:8300` once per second:

```json
[{"id": "RED1567890", "sensor": "R30", "type": "Radar",
  "lla": [40.3471, -111.780331, 1451.35938], ...}]
```

### 6c. Wait for live tracks

> **Time gate:** The prober polls `GET /api/v2/tracks` (using a separate `requests` call, not the shared client) up to every 1–2 seconds (random interval) until it sees at least one track entry with a non-empty `newPoints` array, or until **60 seconds** have elapsed.

If no live tracks appear within 60 seconds, the prober **aborts the entire run** with an error — the snapshot would be useless because all track endpoints would record empty schemas.

### 6d. Track endpoint probe

With live tracks confirmed, the prober runs the full matrix + ablation cycle against a filtered set of endpoints:

- `/datastream/config` — read-only: `POST`, `PUT`, `DELETE` are all skipped, only `GET` runs
- `/api/v2/tracks` and all sub-paths
- `/api/v2/reports/tracks` and all sub-paths
- All endpoints marked `with_tracks_only: true` (the camera endpoints)

The `GET /api/v2/tracks` retry logic described in section 4d is active here (up to 20 retries).

On the `/api/v2/tracks` response, the `newPoints` arrays inside each track entry are replaced with `[]` before the schema is recorded. This is intentional — `newPoints` contains live position updates that change every second, and recording its contents would cause false schema diffs between runs. The field's existence and its type (`array`) are still captured.

### 6e. Teardown

The UDP sender thread is stopped and the fresh HTTP client is closed.

---

## 7. Per-request retry behavior

Every single HTTP request — whether in the matrix, ablation, param resolution, or baseline — goes through the same retry wrapper with up to **3 retries** (4 total attempts):

| Condition | Behaviour |
|---|---|
| **401 Unauthorized** | Refresh the Bearer token immediately, retry. |
| **429 Too Many Requests** | Read the `Retry-After` header (default: 5 seconds), sleep that long, retry. |
| **5xx Server Error** | Sleep **2 seconds**, retry. Only 2 retries allowed for 5xx (not the full 3). |
| **Connection/timeout error** | Sleep **3 seconds**, retry. Only 2 retries allowed. |
| **`--delay` flag** | After every successful response, sleep the configured delay (default: 0). Applies to all requests, not just retries. |

After all retries are exhausted, the last response (or the last exception) is returned/raised.

---

## 8. Cleanup and output

After all scenario probing finishes — **even if an error was thrown** — a `try/finally` block restores all Docker containers to the state they were in when the prober started.

The auth refresh thread is stopped and the HTTP client is closed.

The prober then:

1. Assembles all per-endpoint results into a single snapshot JSON and writes it to `results/<version>/<run_id>.json`.
2. Generates an HTML run report and writes it to `results/<version>/<run_id>.report.html`.
