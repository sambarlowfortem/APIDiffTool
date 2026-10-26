# Probe Detail — Endpoint by Endpoint

Every request the probe sends, in the exact order it sends them. Use this to trace why a GET might be returning empty data.

## How to read this document

**Method order notation:** `POST → PUT → GET → DELETE` means those four requests are sent left to right. Methods in ~~strikethrough~~ are skipped via `skip_methods`. Methods marked `[unlisted]` are sent (the probe checks whether the endpoint exists) but carry no body — only listed methods with a body defined in the YAML get a request body.

**Parameter resolution:** When a path contains `{id}` or similar, the ParamResolver makes a separate dependency call *before* the four methods run. That call is shown as `[param resolution: ...]`. If the dependency call returns empty data, *all four methods fail with `param_resolution_failed`* — no requests are sent.

**Pre-create calls:** Some endpoints have `pre_create` steps that fire before the method loop — shown as `[pre-create: ...]`.

**Cleanup:** After all four methods complete, the probe attempts to DELETE any resource created by the POST call — shown as `[cleanup: ...]`. This is a best-effort silent DELETE; it does not affect the results already recorded.

**Ablation:** After the matrix pass completes for the whole scenario, ablation re-sends POST and PUT requests field-by-field. These are additional requests beyond what is listed below. They only run if the baseline POST/PUT returned 2xx.

**Passes:** Endpoints are grouped by which probe pass they run in:
- **no_containers** — the first (default) pass. Runs most endpoints.
- **containers_present** — second pass. *Only* runs DroneHunter/DroneHangar endpoints.
- **with_tracks** — third pass. Runs tracks, reports/tracks, cameras, and datastream/config.

Endpoints marked `[with_tracks only]` do **not** appear in no_containers or containers_present.

---

## no_containers pass

This is the main pass. All endpoints below run unless otherwise noted. YAML order is the processing order.

---

### Application / Settings

---

**`/api/v2/system/settings/service/{service}`**
- Param resolution: `{service}` = hardcoded value `"skydome"` (no dependency call needed)
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/settings/view/{view}`**
- Param resolution: `{view}` = hardcoded value `"main"`
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/settings/serviceview/{service}/{view}`**
- Param resolution: `{service}` = `"skydome"`, `{view}` = `"main"`
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/settings/keys`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/settings/reset`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/settings`**
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"filterInAirStationary": false}`
- Ablation after matrix: PUT field-by-field (only `filterInAirStationary`)

---

### Customer

---

**`/api/v2/system/customer`**
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [listed, no body] → DELETE [unlisted, no body]`
- PUT body: `{"name": "probe-customer", "timeZone": "America/Denver"}`
- Ablation after matrix: PUT fields `name`, `timeZone`

---

**`/api/v2/system/customer/distance-marker`**
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- ⚠️ NOTE: PUT is listed but has no body defined — the comment says the write is broken server-side; body intentionally omitted to test presence without corrupting state.

---

**`/api/v2/system/licensekey`**
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"key": "probe-license-key-placeholder"}`
- Ablation after matrix: PUT field `key`

---

### Dashboard

---

**`/api/v2/reports/dashboard`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- ⚠️ ORDERING NOTE: GET /api/v2/reports/dashboard runs here. Its response `_id` field is the dependency for `/api/v2/reports/dashboard/{id}` below. If GET returns empty (no dashboards in the system), param resolution for that endpoint will fail.

---

**`/api/v2/reports/dashboard/interval`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/reports/dashboard/{id}`**
- ⚠️ Param resolution: calls `GET /api/v2/reports/dashboard`, takes `_id` from first result. If GET returned empty above, this fails and no requests are sent.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [listed, no body]`

---

### Dropped Locations

---

**`/api/v2/dropped-locations`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"name": "probe-drop", "lat": 40.348, "lon": -111.758, "alt": 1350.0}`
- Cleanup after matrix: `DELETE /api/v2/dropped-locations/{id}` using `_id` from POST response
- ⚠️ ORDERING NOTE: POST runs before GET — the POST-created item should be visible when GET runs. The cleanup DELETE fires *after* GET.
- Ablation after matrix: POST fields `name`, `lat`, `lon`, `alt`

---

**`/api/v2/dropped-locations/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/dropped-locations`, takes `_id`. This is a *fresh* POST call made by the ParamResolver, separate from the matrix POST above.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [listed, no body]`
- PUT body: `{"name": "probe-drop-updated", "lat": 40.348, "lon": -111.758, "alt": 1350.0}`
- Ablation after matrix: PUT fields `name`, `lat`, `lon`, `alt`

---

### Map

---

**`/api/v2/map/config`** — deprecated since 5.0.0
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/map/styles`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/map/system-center`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

### Notifications

---

**`/api/v2/system/notifications`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"type": 3, "level": 4, "source": "probe", "hud": [], "title": "probe-notification", "detail": "Created by API prober", "flagged": false, "ackAllowed": true}`
- Cleanup after matrix: `DELETE /api/v2/system/notifications/{id}` using `_id` from POST response
- ⚠️ ORDERING NOTE: POST runs before GET.
- Ablation after matrix: POST fields `type`, `level`, `source`, `hud`, `title`, `detail`, `flagged`, `ackAllowed`

---

**`/api/v2/system/notifications/latest`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/notifications/audit`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/notifications/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/system/notifications`, takes `_id`. Fresh call.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [listed, no body] → DELETE [listed, no body]`
- PUT body: `{"type": 3, "level": 4, "source": "probe", "hud": [], "title": "probe-notification-updated", "detail": "Updated by API prober", "flagged": false, "ackAllowed": true}`
- Ablation after matrix: PUT fields `type`, `level`, `source`, `hud`, `title`, `detail`, `flagged`, `ackAllowed`

---

**`/api/v2/system/notifications/acknowledge/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/system/notifications`, takes `_id`. Likely returns cached result from above.
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT listed but no body defined (acknowledge is a signal, no payload needed).

---

### Rules

---

**`/api/v2/rules`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: *(large rule object)* — key fields: `name: "probe-rule"`, `active: true`, `condition: "agl > 5"`, `saveTrack: false`, `cancelRepeatingActions: false`, `multiActionTypes: ["ChangeThreat"]`, `threatLevel: -1`, `repeatRuleCheck: 0`, `tags: []`, `zoneTrigger`, `email`, `sms`, `notification`, `changeThreat`, `rangeAlarm`, `groundControl`, `api`
- Cleanup after matrix: `DELETE /api/v2/rules/{id}` using `_id` from POST response
- ⚠️ ORDERING NOTE: POST runs before GET.
- Ablation after matrix: every top-level field of the POST body

---

**`/api/v2/rules/conditions`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/rules/test`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"name": "probe-rule-test", "active": true, "condition": "agl > 5", "saveTrack": false, "cancelRepeatingActions": false, "multiActionTypes": [], "threatLevel": -1, "repeatRuleCheck": 0, "tags": []}`
- Cleanup after matrix: attempted (POST response likely doesn't contain a clean `_id`, so cleanup probably silently fails)
- Ablation after matrix: POST fields

---

**`/api/v2/rules/validate-condition`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"condition": "agl > 5"}`
- Ablation after matrix: POST field `condition`

---

**`/api/v2/rules/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/rules`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [listed, no body]`
- PUT body: `{"name": "probe-rule-updated", "active": true, "condition": "agl > 10", "saveTrack": false, "cancelRepeatingActions": false, "multiActionTypes": [], "threatLevel": -1, "repeatRuleCheck": 0, "tags": []}`
- Ablation after matrix: PUT fields

---

### Service / Site

---

**`/api/v2/service/restart`**
- ⚠️ SKIP: `skip_methods: [POST, PUT, DELETE]` — only GET is sent.
- Sends: `GET [unlisted, no body]`

---

**`/api/v2/service/shutdown`**
- ⚠️ SKIP: `skip_methods: [POST, PUT, DELETE]` — only GET is sent.
- Sends: `GET [unlisted, no body]`

---

**`/api/v2/app/state`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/app/gps`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/app/backups`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- ⚠️ ORDERING NOTE: GET /api/v2/app/backups runs here. Its `name` field is the dependency for `/api/v2/app/backups/{backup}` below. If no backups exist, that param resolution fails.

---

**`/api/v2/app/backups/{backup}`**
- ⚠️ Param resolution: calls `GET /api/v2/app/backups`, takes `name`. If GET above returned empty, this fails.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/service/network`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"mqttHost": "172.16.0.250", "mqttPort": 1883, "mapsHost": "172.16.0.250", "mapsPort": 8089, "skydomeHost": "172.16.0.250", "skydomePort": 80, "interface": ["enp0s1"], "ips": ["dhcp"], "nameservers": [["8.8.8.8"]], "gateway": "172.16.0.1", "dhcp": true}`
- Ablation after matrix: POST fields

---

### Time Servers

---

**`/api/v2/system/time-servers`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"host": "pool.ntp.org", "enabled": true}`
- Cleanup after matrix: `DELETE /api/v2/system/time-servers/{host}` — *note: cleanup uses `host` not `_id`*
- ⚠️ ORDERING NOTE: POST runs before GET.
- Ablation after matrix: POST fields `host`, `enabled`

---

**`/api/v2/system/time-servers/sync`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/time-servers/{host}`**
- ⚠️ Param resolution: calls `POST /api/v2/system/time-servers`, takes `host` field. Fresh call.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [listed, no body]`
- PUT body: `{"enabled": true}`
- Ablation after matrix: PUT field `enabled`

---

### Users

---

**`/api/v2/system/users`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"active": true, "email": "probe-user@fortemtech.com", "emailReset": false, "fname": "Probe", "lname": "User", "role": "user", "prefs": {"language": "en", "maps": {...}}}`
- Cleanup after matrix: `DELETE /api/v2/system/users/{id}` using `_id` from POST response
- ⚠️ ORDERING NOTE: POST runs before GET. The newly created user should be visible in GET.
- Ablation after matrix: POST top-level fields

---

**`/api/v2/system/users/logout`**
- Sends: `POST [listed, NO BODY] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- ⚠️ NOTE: This POSTs to the logout endpoint. If the server actually logs out the current session this would break all subsequent requests. In practice the server typically requires a body/session token and returns an error for a bare POST.

---

**`/api/v2/system/users/check-access`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/users/login`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"email": "tech@fortemtech.com", "password": "Dr0nehunter!"}`
- NOTE: This logs in as the hardcoded probe credentials. The resulting token is NOT used by the probe — the auth manager has its own token. This just tests that the endpoint responds.
- Ablation after matrix: POST fields `email`, `password`

---

**`/api/v2/system/users/token/refresh`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/users/eula`**
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT listed but no body defined.

---

**`/api/v2/system/users/preferences`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"language": "en", "maps": {"easeToCenter": true, "defaultMap": {"bearing": 0, "lat": 40.35062, "lng": -111.760567, "pitch": 1, "zoom": 14}}}`
- Ablation after matrix: POST fields `language`, `maps`

---

**`/api/v2/system/users/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/system/users`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [listed, no body]`
- PUT body: `{"active": true, "email": "probe-user-updated@fortemtech.com", "fname": "ProbeUpdated", "lname": "User"}`
- Ablation after matrix: PUT fields

---

**`/api/v2/system/users/update-sms/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/system/users`, takes `_id`. Likely cached.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"smsNumber": "", "smsCarrier": null}`
- Ablation after matrix: PUT fields `smsNumber`, `smsCarrier`

---

**`/api/v2/system/users/{id}/password`**
- ⚠️ Param resolution: calls `POST /api/v2/system/users`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"password": "Probe123!"}`
- Ablation after matrix: PUT field `password`

---

**`/api/v2/system/users/{id}/reset-password`**
- ⚠️ Param resolution: calls `POST /api/v2/system/users`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT listed but no body defined.

---

**`/api/v2/system/users/{id}/confirm-sms-code`**
- ⚠️ Param resolution: calls `POST /api/v2/system/users`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"code": 0}`
- Ablation after matrix: PUT field `code`

---

**`/api/v2/system/users/{id}/generate-sms-code`**
- ⚠️ Param resolution: calls `POST /api/v2/system/users`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"smsNumber": "1 (555) 555-5555", "smsCarrier": {"name": "Verizon Wireless", "domain": "vtext.com"}}`
- Ablation after matrix: PUT fields `smsNumber`, `smsCarrier`

---

**`/api/v2/system/users/roles`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/system/users/admin/setup`**
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"user": {}, "newPass": "probe-placeholder"}`
- Ablation after matrix: PUT fields `user`, `newPass`

---

**`/api/v2/system/user`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

### Zones

---

**`/api/v2/zones`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"name": "probe-zone", "featureId": "probe-zone-feature", "path": [[40.346,-111.797], [40.346,-111.798], [40.345,-111.798], [40.345,-111.797], [40.346,-111.797]], "floor": 10, "ceiling": 200, "kind": "regular", "active": true, "notes": "", "styles": {...}}`
- Cleanup after matrix: `DELETE /api/v2/zones/{id}` using `_id` from POST response
- ⚠️ ORDERING NOTE: POST runs before GET.
- Ablation after matrix: POST top-level fields

---

**`/api/v2/zones/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/zones`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [listed, no body]`
- PUT body: zone update with `name: "probe-zone-updated"`, same path/floor/ceiling/kind/active
- Ablation after matrix: PUT top-level fields

---

### Reports — Tracks

⚠️ **IMPORTANT:** All `/api/v2/reports/tracks` endpoints run in the **no_containers** pass (they are NOT flagged `with_tracks_only`). In no_containers, there may be no track history in the system, so GET responses are likely empty and param resolution for `{id}` endpoints will fail.

---

**`/api/v2/reports/tracks/categories`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/reports/tracks`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- ⚠️ ORDERING NOTE: The `id` field from this GET response is the dependency for the `{id}` endpoints below. If GET returns empty (no saved track reports), those endpoints fail at param resolution.

---

**`/api/v2/reports/tracks/{id}/prepare-recordings`**
- ⚠️ Param resolution: calls `GET /api/v2/reports/tracks`, takes `id`. If no track reports exist, fails.
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"stream_type": "optical"}`
- Ablation after matrix: POST field `stream_type`

---

**`/api/v2/reports/tracks/delete-multiple`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [listed, NO BODY]`
- DELETE is listed but no body is defined (body format unknown per hand-check notes).

---

**`/api/v2/reports/tracks/{id}`**
- ⚠️ Param resolution: calls `GET /api/v2/reports/tracks`, takes `id`. Same issue as above.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [listed, no body] → DELETE [listed, no body]`
- PUT body: `{"id": "probe-track", "start": 1613093218032, "end": 1613093237791, "tags": [], "threatLevel": 0, "displayCategory": true}`
- Ablation after matrix: PUT fields `id`, `start`, `end`, `tags`, `threatLevel`, `displayCategory`

---

### Reports — Logs

---

**`/api/v2/reports/logs/download`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/reports/logs/create-bug-log`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

### Radars

---

**`/api/v2/sensors/radars`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: full radar object with `host: "172.16.0.47"`, `port: 9991`, `configPort: 9990`, `model: "R40"`, `id: "X00330136"`, `name: "Radar X00330136"`, plus full `config` sub-object (position, advanced, standard, hotspotMasks, multiRdr), `horizontalFOV`, `verticalFOV`, and misc fields
- Cleanup after matrix: `DELETE /api/v2/sensors/radars/{id}` using `_id` from POST response
- ⚠️ ORDERING NOTE: POST runs before GET. The radar should be visible in GET.
- ⚠️ NOTE: `_id` from this POST is the dependency for all the `{id}` radar sub-endpoints below. `host` and `port` from the POST body are the dependencies for `{host}/{port}` endpoints.
- Ablation after matrix: POST top-level fields

---

**`/api/v2/sensors/radars/{host}/{port}/test`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/radars`, takes `host` and `port` from POST body fields.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/radars/{host}/{port}/health-check`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/radars`, takes `host` and `port`.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/radars/{host}/{port}/config`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/radars`, takes `host` and `port`.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/radars/{id}/refresh-connection`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/radars`, takes `_id`.
- Sends: `POST [listed, NO BODY] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/radars/{id}/move`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/radars`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"lat": 40.348, "lon": -111.758, "alt": 1350.0, "yaw": 90}`
- Ablation after matrix: PUT fields `lat`, `lon`, `alt`, `yaw`

---

**`/api/v2/sensors/radars/start-sys-pos`**
- Sends: `POST [listed, NO BODY] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/radars/start-calibration`**
- Sends: `POST [listed, NO BODY] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/radars/stop-calibration`**
- Sends: `POST [listed, NO BODY] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/radars/{id}/mode`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/radars`, takes `_id`.
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"id": "X00330136", "transmit": true, "host": "172.16.0.47", "port": 9991, "configPort": 9990, "model": "R40", "name": "Radar X00330136"}`
- Ablation after matrix: POST fields

---

**`/api/v2/sensors/radars/relocate`** — removed from docs since 5.1.0
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY — body is an array, ablation skipped] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- NOTE: PUT body is a JSON array (not object); ablation loop skips it and sets `body_not_object_skipped_ablation` flag.

---

**`/api/v2/sensors/radars/bulk-edit`**
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"ids": [], "transmit": true, "elevationFilters": {"useTrackElevationFilter": false, "minTrackAglMeters": 0, "maxTrackAglMeters": 0}}`
- Ablation after matrix: PUT fields `ids`, `transmit`, `elevationFilters`

---

**`/api/v2/sensors/radars/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/radars`, takes `_id`.
- ⚠️ SKIP: `skip_methods: [PUT]` — PUT is not sent.
- Sends: `POST [unlisted, no body] → GET [unlisted, no body] → DELETE [listed, no body]`

---

**`/api/v2/sensors/radars/delete-multiple`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [listed, NO BODY]`

---

### Tracks

⚠️ **IMPORTANT:** These endpoints run in the **no_containers** pass where there may be no live tracks. GET /api/v2/tracks will likely return empty data, causing param resolution to fail for all `{id}` track sub-endpoints. The probe does NOT retry empty GETs in the no_containers pass — retry logic only activates in the with_tracks pass. These endpoints also run again in the **with_tracks** pass with live data.

---

**`/api/v2/tracks`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"sensorId": "probe-sensor", "points": [{}]}`
- ⚠️ ORDERING NOTE: POST runs before GET. However, whether a manually-injected track via this endpoint shows up in GET depends on server behaviour. In no_containers there are typically no organic tracks. GET may still return empty even after POST.
- ⚠️ ORDERING NOTE: GET /api/v2/tracks is the dependency for all `{id}` track endpoints AND for DroneHunter `{trackId}` endpoints. If GET returns empty here, those all fail at param resolution.
- Ablation after matrix: POST fields `sensorId`, `points`

---

**`/api/v2/tracks/paths`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/tracks/current`**
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [listed, no body] → DELETE [unlisted, no body]`
- PUT body: `{"id": "probe-track-id"}`
- Ablation after matrix: PUT field `id`

---

**`/api/v2/tracks/{id}`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`. If GET returned empty above, this fails.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/tracks/paths/{id}`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/tracks/cot`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"xml": "<event/>"}`
- Ablation after matrix: POST field `xml`

---

**`/api/v2/tracks/{id}/ignore`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`.
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/tracks/queue`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"type": "radar", "points": [{}]}`
- Ablation after matrix: POST fields `type`, `points`

---

**`/api/v2/tracks/{id}/custom-rf-track-action`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/tracks/rf-track/{id}/mitigate`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`.
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"type": "probe", "coords": []}`
- Ablation after matrix: POST fields `type`, `coords`

---

**`/api/v2/tracks/{id}/set-manual-threat`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"threatLevel": 0}`
- Ablation after matrix: PUT field `threatLevel`

---

**`/api/v2/tracks/{id}/object-of-interest`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`.
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

### RF Sensors

---

**`/api/v2/sensors/rfsensors`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"model": "WhiteFox", "name": "probe-rfsensor", "host": "172.16.0.47", "port": 9992, "username": "test", "password": "test", "latitude": 0, "longitude": 0, "altitude": 0, "yaw": 0, "simulated": false}`
- ⚠️ CLEANUP NOTE: RF sensors are deleted via `DELETE /api/v2/sensors/radars/{id}` (not the rfsensors path). The `cleanup_path_prefix: /api/v2/sensors/radars` field handles this. After POST succeeds, cleanup sends `DELETE /api/v2/sensors/radars/{_id}`.
- ⚠️ ORDERING NOTE: POST runs before GET.
- ⚠️ NOTE: `_id` from POST is the dependency for all `{id}` RF sensor sub-endpoints below.
- Ablation after matrix: POST top-level fields

---

**`/api/v2/sensors/rfsensors/{id}/turn-jammer`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/rfsensors`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"pan": 0, "deviceId": "probe-device"}`
- Ablation after matrix: PUT fields `pan`, `deviceId`

---

**`/api/v2/sensors/rfsensors/directional-jammers`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/rfsensors/jam`**
- ⚠️ SKIP: `skip_methods: [POST]` — POST is not sent (triggers real RF jamming hardware).
- Sends: `PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/rfsensors/{id}`**
- ⚠️ Param resolution: calls `POST /api/v2/sensors/rfsensors`, takes `_id`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"model": "WhiteFox", "name": "probe-rfsensor-updated", "host": "172.16.0.47", "username": "test", "password": "test"}`
- Ablation after matrix: PUT fields `model`, `name`, `host`, `username`, `password`

---

### DroneHunter — Autonomous / Engagement

---

**`/api/v2/dronehunters/autonomous-deploy`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"trackId": "probe-track-id"}`
- Ablation after matrix: POST field `trackId`

---

**`/api/v2/dronehunters/autonomous-engage-position`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"neutralizationMode": "ANY", "lat": 40.348, "lon": -111.758, "alt": 1450.0, "azm": 0}`
- Ablation after matrix: POST fields

---

**`/api/v2/dronehunters/autonomous-engage-target`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"neutralizationMode": "ANY", "trackId": "probe-track-id"}`
- Ablation after matrix: POST fields

---

*(The following DroneHunter `{id}` engagement endpoints all follow the same pattern: param resolution via `GET /api/v2/dronehunters` → `hunter_id`. They all run in no_containers, meaning the DroneHunter container is NOT running. If the DH container is stopped, GET /api/v2/dronehunters likely returns empty → param resolution fails for all `{id}` engagement endpoints.)*

**`/api/v2/dronehunters/{id}/capture`**, **`/api/v2/dronehunters/{id}/flight-command`**, **`/api/v2/dronehunters/{id}/one-time-command`**, **`/api/v2/dronehunters/{id}/artemis/abort`**, **`/api/v2/dronehunters/{id}/engage-position`**, **`/api/v2/dronehunters/{id}/engage-target`**, **`/api/v2/dronehunters/{id}/set-rules-of-engagement`**, **`/api/v2/dronehunters/{id}/position-src`**, **`/api/v2/dronehunters/{id}/ekf-pos-source-failsafe`**, **`/api/v2/dronehunters/{id}/set-gps-denied-origin`**, **`/api/v2/dronehunters/{id}/drop-payload`**
- ⚠️ Param resolution: all call `GET /api/v2/dronehunters`, take `hunter_id`. In no_containers, likely fails.
- Each sends POST with its specific body (or no body if none defined)

---

### Sensors — Devices / Other

---

**`/api/v2/sensors/devices`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [listed, body below]`
- POST body: `{"clientId": "probe-client", "type": "radar"}`
- DELETE body: `{"clientId": "probe-client", "type": "radar"}` — ⚠️ NOTE: DELETE has a body, which is unusual. The body is sent because DELETE is listed and has a body defined. However, `WRITABLE_METHODS = {"POST", "PUT"}` — DELETE is not in WRITABLE_METHODS, so the body will NOT be sent. DELETE will be sent with no body.
- Ablation after matrix: POST fields `clientId`, `type`

---

**`/api/v2/sensors/firefly/fovs`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/sensors/radars/playbackMode/command`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

### System Health

---

**`/api/v2/system/health`**
- Sends: `POST [listed, NO BODY] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- NOTE: POST is a stub; server returns "this endpoint is still under development."

---

**`/api/v2/system/health/{id}`**
- Param resolution: `{id}` = hardcoded value `"probe-health-id"` (no dependency call)
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [listed, NO BODY]`
- NOTE: Both PUT and DELETE are stubs.

---

### App — System Management

---

**`/api/v2/download`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/app/set-system-time`**
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"timeString": "2026-01-01T00:00:00Z"}`
- Ablation after matrix: POST field `timeString`

---

**`/api/v2/app/reset-system-setup`**
- ⚠️ SKIP: `skip_methods: [POST]` — POST is not sent (would wipe admin credentials).
- Sends: `PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/tracks/update-live-track`**
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"id": "probe-track-id"}`
- Ablation after matrix: PUT field `id`

---

## containers_present pass

Only runs if `containers_present` is in the `--scenarios` list (it is by default). The probe filters the registry to **only** DroneHunter/DroneHangar endpoints for this pass. Everything else was already covered in no_containers.

Before probing, the probe starts `dronehangar` and `dronehunter-1`, stops `dronehunter-2` and `dronehunter-3`, then polls the API for up to 20 seconds until it reflects those counts.

---

### DroneHangar

---

**`/api/v2/dronehunters/hangars`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- ⚠️ ORDERING NOTE: GET /api/v2/dronehunters/hangars is the dependency for all `{hangarId}` endpoints. With `dronehangar` container running, this should return data.

---

**`/api/v2/dronehunters/hangars/set-lla/{hangarId}`**
- ⚠️ Param resolution: calls `GET /api/v2/dronehunters/hangars`, takes `clientId`.
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- PUT body: `{"lat": 40.348, "lon": -111.758, "alt": 1350.0}`
- Ablation after matrix: PUT fields `lat`, `lon`, `alt`

---

**`/api/v2/dronehunters/hangars/{hangarId}/{action}`**
- ⚠️ Param resolution: `{hangarId}` from `GET /api/v2/dronehunters/hangars` → `clientId`; `{action}` = hardcoded `"open"`
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/dronehunters/hangars/{hangarId}/hunter/{hunterId}`**
- ⚠️ Param resolution: `{hangarId}` from `GET /api/v2/dronehunters/hangars` → `clientId`; `{hunterId}` from `GET /api/v2/dronehunters` → `hunter_id`
- Sends: `POST [unlisted, no body] → PUT [listed, NO BODY] → GET [unlisted, no body] → DELETE [unlisted, no body]`

---

### DroneHunter

---

**`/api/v2/dronehunters`**
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- ⚠️ ORDERING NOTE: GET /api/v2/dronehunters is the dependency for all DroneHunter `{id}` and `{hunterId}` endpoints. With `dronehunter-1` container running, this should return data. `hunter_id`, `host`, and `port` are all extracted from this response.

---

**`/api/v2/dronehunters/{host}/{port}/hunters`**
- ⚠️ Param resolution: calls `GET /api/v2/dronehunters`, takes `host` and `port`.
- Sends: `POST [unlisted, no body] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`

---

**`/api/v2/dronehunters/{id}/defend`**
- ⚠️ Param resolution: calls `GET /api/v2/dronehunters`, takes `hunter_id`.
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"lat": 40.348, "lon": -111.758, "alt": 1450.0, "azm": 0}`
- Ablation after matrix: POST fields

---

**`/api/v2/dronehunters/{id}/defend-track`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"trackId": "probe-track-id"}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/land`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"immediately": false}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/navigate`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"search": false, "lat": 40.348, "lon": -111.781, "alt": 1451.36}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/stop`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST [no body] → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/return-home`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST [no body] → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/send-on-mission`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"points": [[40.348,-111.758,1450]], "kill": false, "trackId": "probe-track-id"}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/send-on-hunt`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"kill": false, "lat": 40.348, "lon": -111.758, "alt": 1450.0}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/set-payload-config`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST [listed, body is a JSON **array** — ablation skipped, `body_not_object_skipped_ablation` flag set] → PUT → GET → DELETE
- POST body: `[{"name": "rightWeapon", "payload_type": "RANGED", "payload_class": "standardNetGun", "payload_function": "ATTACK", "tier": 2, "cartridges_remaining": 1, "max_cartridges": 1}]`

---

**`/api/v2/dronehunters/{id}/set-landing-pad-orientation`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST → PUT `{"roll": 0, "pitch": 0, "yaw": 0}` → GET → DELETE

---

**`/api/v2/dronehunters/{id}/set-height-bounds`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST → PUT `{"floor": 1350, "ceiling": 2500}` → GET → DELETE

---

**`/api/v2/dronehunters/{id}/comm-loss-failsafe`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST → PUT `{"mode": "return_home"}` → GET → DELETE

---

**`/api/v2/dronehunters/{id}/calibrate`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"command": "start"}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/cancel-calibrate`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"command": "cancel"}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/get-component-data`**, **`/api/v2/dronehunters/{id}/file-update`**, **`/api/v2/dronehunters/{id}/cancel-update`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST [no body] → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{hunterId}/status`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"status": "probe"}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/tracks/{trackId}/confirm-dispatch`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`. In containers_present, tracks may still be empty.
- Sends: POST `{"confirm": true}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/tracks/{trackId}/manual-hunt`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`. Same issue.
- Sends: POST `{"status": "hunt"}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/toggle-accessory/{accessory}/{toggle}`**
- ⚠️ Param resolution: `{id}` from `GET /api/v2/dronehunters` → `hunter_id`; `{accessory}` = `"light"`, `{toggle}` = `"on"`
- Sends: POST [no body] → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/override-low-battery-rtl`**, **`/api/v2/dronehunters/{id}/start-stream`**, **`/api/v2/dronehunters/{id}/stop-stream`**, **`/api/v2/dronehunters/{id}/pair`**, **`/api/v2/dronehunters/{id}/unpair`**, **`/api/v2/dronehunters/{id}/add-to-pool`**, **`/api/v2/dronehunters/{id}/remove-from-pool`**
- ⚠️ Param resolution: all via `GET /api/v2/dronehunters` → `hunter_id`
- All send POST [no body] → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/set-time-slot`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"timeslot": 1}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/retrieve-flight-log`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/dronehunters/{id}/set-alt-offset`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"clear": false, "alt": 0}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/set-config`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"file": "probe", "param": "probe", "value": "probe"}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/set-require-radar-gps`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"value": false}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/total-dh-streams`**
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/dronehunters/{id}/hunt`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"kill": false, "trackId": "probe-track-id"}` → PUT → GET → DELETE

---

**`/api/v2/dronehunters/{id}/gnss`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST `{"enable": true}` → PUT → GET → DELETE

---

### DroneHunter — Defend Points

---

**`/api/v2/dronehunters/defend-points`**
- Pre-create: `DELETE /api/v2/dronehunters/defend-points/probe-defend-point` (clean up any leftover from a prior run)
- Sends: `POST [listed, body below] → PUT [unlisted, no body] → GET [listed, no body] → DELETE [unlisted, no body]`
- POST body: `{"name": "probe-defend-point", "lat": 40.348, "lon": -111.758, "radius": 100}`
- Cleanup after matrix: `DELETE /api/v2/dronehunters/defend-points/probe-defend-point` (uses `name` as the ID via `cleanup_id_field`)
- ⚠️ ORDERING NOTE: POST runs before GET. The probe-defend-point should be visible in GET.
- Ablation after matrix: POST fields

---

**`/api/v2/dronehunters/defend-points/{name}`**
- ⚠️ Param resolution: calls `POST /api/v2/dronehunters/defend-points`, takes `name` field.
- Sends: POST [unlisted] → PUT [unlisted] → GET [unlisted] → DELETE [listed, no body]

---

### DroneHunter — Land Zones

---

**`/api/v2/dronehunters/land-zones`**
- Pre-create: `DELETE /api/v2/dronehunters/land-zones/probe-land-zone`
- Sends: `POST [listed, body below] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]`
- POST body: `{"name": "probe-land-zone", "lat": 40.348, "lon": -111.758, "alt": 1350.0}`
- Cleanup after matrix: `DELETE /api/v2/dronehunters/land-zones/probe-land-zone`
- ⚠️ ORDERING NOTE: POST runs before GET.
- Ablation after matrix: POST fields

---

**`/api/v2/dronehunters/land-zones/{name}`**
- Param: `{name}` = hardcoded `"probe-land-zone"`
- Pre-create (in order):
  1. `DELETE /api/v2/dronehunters/land-zones/probe-land-zone`
  2. `POST /api/v2/dronehunters/land-zones` body: `{"name": "probe-land-zone", ...}`
- Sends: POST [unlisted] → PUT [listed, body `{"lat": 40.349, "lon": -111.759, "alt": 1351.0}`] → GET [unlisted] → DELETE [listed, no body]
- Ablation after matrix: PUT fields

---

**`/api/v2/dronehunters/{id}/land-zones/assign`**
- ⚠️ Param resolution: `{id}` from `GET /api/v2/dronehunters` → `hunter_id`. Falls back to `"999"` if empty.
- Pre-create (in order):
  1. `DELETE /api/v2/dronehunters/land-zones/probe-land-zone`
  2. `POST /api/v2/dronehunters/land-zones` body: `{"name": "probe-land-zone", ...}`
- Sends: POST [listed, `{"name": "probe-land-zone"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST field `name`

---

**`/api/v2/dronehunters/{id}/land-zones/unassign`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST [listed, no body] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]

---

**`/api/v2/dronehunters/{id}/land-zones/override-alt`**
- ⚠️ Param resolution: `{id}` from `GET /api/v2/dronehunters` → `hunter_id`. Falls back to `"999"` if empty.
- Pre-create (in order):
  1. `DELETE /api/v2/dronehunters/land-zones/probe-land-zone`
  2. `POST /api/v2/dronehunters/land-zones` body: `{"name": "probe-land-zone", ...}`
  3. `POST /api/v2/dronehunters/{id}/land-zones/assign` body: `{"name": "probe-land-zone"}` — uses the resolved `{id}` param
- Sends: POST [listed, `{"alt": 1350.0}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST field `alt`

---

### DroneHunter — Drop Zones

---

**`/api/v2/dronehunters/drop-zones`**
- Sends: POST [listed, `{"name": "probe-drop-zone", "lat": 40.348, "lon": -111.758, "alt": 1350.0}`] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]
- ⚠️ ORDERING NOTE: POST runs before GET.
- Ablation after matrix: POST fields

---

**`/api/v2/dronehunters/drop-zones/{name}`**
- Param: `{name}` = hardcoded `"probe-drop-zone"`
- Pre-create (in order):
  1. `DELETE /api/v2/dronehunters/drop-zones/probe-drop-zone`
  2. `POST /api/v2/dronehunters/drop-zones` body: `{"name": "probe-drop-zone", ...}`
- Sends: POST [unlisted] → PUT [listed, `{"lat": 40.349, "lon": -111.759, "alt": 1351.0}`] → GET [unlisted] → DELETE [listed, no body]
- Ablation after matrix: PUT fields

---

**`/api/v2/dronehunters/{id}/drop-zones/assign`**
- ⚠️ Param resolution: `{id}` from `GET /api/v2/dronehunters` → `hunter_id`. Falls back to `"999"`.
- Pre-create (in order):
  1. `DELETE /api/v2/dronehunters/drop-zones/probe-drop-zone`
  2. `POST /api/v2/dronehunters/drop-zones` body: `{"name": "probe-drop-zone", ...}`
- Sends: POST [listed, `{"name": "probe-drop-zone"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST field `name`

---

**`/api/v2/dronehunters/{id}/drop-zones/unassign`**
- ⚠️ Param resolution: `GET /api/v2/dronehunters` → `hunter_id`
- Sends: POST [listed, no body] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]

---

**`/api/v2/dronehunters/{id}/drop-zones/override-alt`**
- ⚠️ Param resolution: `{id}` from `GET /api/v2/dronehunters` → `hunter_id`. Falls back to `"999"`.
- Pre-create (in order):
  1. `DELETE /api/v2/dronehunters/drop-zones/probe-drop-zone`
  2. `POST /api/v2/dronehunters/drop-zones` body: `{"name": "probe-drop-zone", ...}`
  3. `POST /api/v2/dronehunters/{id}/drop-zones/assign` body: `{"name": "probe-drop-zone"}` — uses resolved `{id}`
- Sends: POST [listed, `{"alt": 1350.0}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST field `alt`

---

### DroneHunter — Ground Control

---

**`/api/v2/dronehunters/groundcontrol`**
- Sends: POST [unlisted] → PUT [listed, body below] → GET [listed, no body] → DELETE [unlisted]
- PUT body: `{"gc_desc": "Default Ground Control", "hostName": "ground-control", "port": 8083, "default_ceiling": 3001, "default_floor": 0, "max_drop_zone_distance": 100, "max_land_zone_distance": 100, "status": "available"}`
- ⚠️ ORDERING NOTE: GET runs after PUT — the PUT may have already changed the GC state.
- Ablation after matrix: PUT fields

---

**`/api/v2/dronehunters/groundcontrol/{host}/{port}`**
- Param: `{host}` = hardcoded `"ground-control"`, `{port}` = hardcoded `"8083"`
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/dronehunters/groundcontrol/radio`**
- Sends: POST [listed, `{"address": "probe-address", "config": "probe-config", "value": "probe-value"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields

---

**`/api/v2/dronehunters/groundcontrol/set-registered-radio`**
- ⚠️ NOTE: Body must use real Microhard values — probe-placeholder values cause a permanent server-side corruption bug requiring full system reset.
- Sends: POST [listed, `{"model": "Microhard", "address": "172.16.10.10"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields `model`, `address`

---

**`/api/v2/dronehunters/groundcontrol/radio-frequency-settings`**
- Sends: POST [listed, large body with radio config] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]
- POST body: `{"address": "172.16.10.10", "bandwidth_bytes_in": -1, ..., "make": "Microhard", "model": "pDDL1800-AES256", "network_id": "FTxDH", ...}` (full radio settings object)
- ⚠️ ORDERING NOTE: POST runs before GET.
- Ablation after matrix: POST top-level fields

---

**`/api/v2/dronehunters/get-global-rules-of-engagement`**
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/dronehunters/set-global-rules-of-engagement`**
- Sends: POST [listed, `{"acquire_targets": true, "default_mission": "defend", "weapons_enabled": false}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields

---

**`/api/v2/dronehunters/remove-tracks-from-pool`**
- Sends: POST [listed, `{"track_ids": []}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST field `track_ids`

---

**`/api/v2/dronehunters/update-swarm-mitigation-assignments`**
- Sends: POST [listed, `{"hunter_ids": [], "target_ids": [], "target_locations": [], "mission_type": "defend"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields

---

**`/api/v2/dronehunters/toggle_target_assignment`**
- Sends: POST [listed, `{"value": false}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST field `value`

---

### DroneHunter — Height Bounds

---

**`/api/v2/dronehunters/default-height-bounds`**
- Sends: POST [unlisted] → PUT [listed, `{"floor": 1350, "ceiling": 2500}`] → GET [listed, no body] → DELETE [unlisted]
- Ablation after matrix: PUT fields `floor`, `ceiling`

---

### DroneHunter — Geocages

---

**`/api/v2/dronehunters/geocages`**
- Sends: POST [listed, body below] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]
- POST body: `{"name": "probe-geocage", "cage_type": "KEEP_HUNTER_OUT", "ceiling": 2000, "floor": 0, "lat_lon_points": [[40.347846,-111.758030],[40.348031,-111.757816],[40.348133,-111.758022],[40.347979,-111.758175],[40.347846,-111.758030]], "mobile": false, "response_type": "STOP"}`
- Cleanup after matrix: `DELETE /api/v2/dronehunters/geocages/probe-geocage`
- ⚠️ ORDERING NOTE: POST runs before GET.
- Ablation after matrix: POST top-level fields

---

**`/api/v2/dronehunters/geocages/{name}`**
- Param: `{name}` = hardcoded `"probe-geocage"`
- Pre-create (in order):
  1. `DELETE /api/v2/dronehunters/geocages/probe-geocage`
  2. `POST /api/v2/dronehunters/geocages` body: full geocage object
- Sends: POST [unlisted] → PUT [listed, geocage update body with `ceiling: 2100`] → GET [unlisted] → DELETE [listed, no body]
- Ablation after matrix: PUT fields

---

### DroneHunter — Waypoints

*(All 7 waypoint endpoints follow the same pattern)*

**`/api/v2/dronehunters/{id}/waypoints/hover`**
**`/api/v2/dronehunters/{id}/waypoints/attack-track`**
**`/api/v2/dronehunters/{id}/waypoints/attack-position`**
**`/api/v2/dronehunters/{id}/waypoints/defend-track`**
**`/api/v2/dronehunters/{id}/waypoints/defend-direction`**
**`/api/v2/dronehunters/{id}/waypoints/capture-track`**
**`/api/v2/dronehunters/{id}/waypoints/capture-position`**

- ⚠️ Param resolution: all via `GET /api/v2/dronehunters` → `hunter_id`
- Each sends POST [listed, waypoint body] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Bodies include `waypoints` array (3D coordinate lists) plus method-specific fields (`trackId`, `azm`, `position`)

---

## with_tracks pass

This pass uses a fresh HTTP client. Before any endpoint is probed, the track seeder runs (DELETE then POST to `/datastream/config`, then UDP sender starts, then the probe waits up to 60 seconds for live tracks to appear in GET /api/v2/tracks). If no tracks appear within 60 seconds, the entire run aborts.

The filtered endpoint set for this pass is:

- `/datastream/config` (read-only — POST, PUT, DELETE skipped)
- All `/api/v2/tracks/...` paths
- All `/api/v2/reports/tracks/...` paths
- All `with_tracks_only: true` endpoints (cameras)

---

### DataStream

---

**`/datastream/config`**
- ⚠️ CUSTOM ORDER: `probe_order: [DELETE, GET, POST, PUT]` but `skip_methods: [POST, PUT, DELETE]` applied. Only GET runs.
- Sends: `GET [listed, no body]`

---

### Tracks (with live data)

---

**`/api/v2/tracks`**
- Sends: POST [listed, `{"sensorId": "probe-sensor", "points": [{}]}`] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]
- ⚠️ RETRY: GET is retried up to **20 times** with 1–2s random sleep between attempts if response is empty or 429. This is the only endpoint in the entire probe with retry logic on GET.
- ⚠️ SANITIZATION: The `newPoints` arrays inside all track entries in the GET response are replaced with `[]` before the schema is inferred, to prevent false diffs caused by live position data.
- ⚠️ ORDERING NOTE: POST runs before GET. POST creates a synthetic track; live tracks from UDP are also present.
- Ablation after matrix: POST fields `sensorId`, `points`

---

**`/api/v2/tracks/paths`**
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/tracks/current`**
- Sends: POST [unlisted] → PUT [listed, `{"id": "probe-track-id"}`] → GET [listed, no body] → DELETE [unlisted]
- Ablation after matrix: PUT field `id`

---

**`/api/v2/tracks/{id}`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`. With live tracks running, this should succeed.
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/tracks/paths/{id}`**
- ⚠️ Param resolution: calls `GET /api/v2/tracks`, takes `id`.
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/tracks/cot`**
- Sends: POST [listed, `{"xml": "<event/>"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST field `xml`

---

**`/api/v2/tracks/{id}/ignore`**
- ⚠️ Param resolution: `GET /api/v2/tracks` → `id`
- Sends: POST [unlisted] → PUT [listed, no body] → GET [unlisted] → DELETE [unlisted]

---

**`/api/v2/tracks/queue`**
- Sends: POST [listed, `{"type": "radar", "points": [{}]}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields `type`, `points`

---

**`/api/v2/tracks/{id}/custom-rf-track-action`**
- ⚠️ Param resolution: `GET /api/v2/tracks` → `id`
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/tracks/rf-track/{id}/mitigate`**
- ⚠️ Param resolution: `GET /api/v2/tracks` → `id`
- Sends: POST [listed, `{"type": "probe", "coords": []}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields `type`, `coords`

---

**`/api/v2/tracks/{id}/set-manual-threat`**
- ⚠️ Param resolution: `GET /api/v2/tracks` → `id`
- Sends: POST [unlisted] → PUT [listed, `{"threatLevel": 0}`] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: PUT field `threatLevel`

---

**`/api/v2/tracks/{id}/object-of-interest`**
- ⚠️ Param resolution: `GET /api/v2/tracks` → `id`
- Sends: POST [unlisted] → PUT [listed, no body] → GET [unlisted] → DELETE [unlisted]

---

**`/api/v2/tracks/update-live-track`**
- Sends: POST [unlisted] → PUT [listed, `{"id": "probe-track-id"}`] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: PUT field `id`

---

### Reports — Tracks (with live data)

---

**`/api/v2/reports/tracks/categories`**
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/reports/tracks`**
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]
- ⚠️ ORDERING NOTE: Track reports are generated from *completed* tracks in the system's history. Even with live tracks injected by the seeder, there may be no *completed* track reports yet — GET may still return empty if the tracks haven't ended and been processed into reports. The `{id}` endpoints below depend on this GET returning data.

---

**`/api/v2/reports/tracks/{id}/prepare-recordings`**
- ⚠️ Param resolution: `GET /api/v2/reports/tracks` → `id`. May still fail if no completed track reports exist.
- Sends: POST [listed, `{"stream_type": "optical"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST field `stream_type`

---

**`/api/v2/reports/tracks/delete-multiple`**
- Sends: POST [unlisted] → PUT [unlisted] → GET [unlisted] → DELETE [listed, no body]

---

**`/api/v2/reports/tracks/{id}`**
- ⚠️ Param resolution: `GET /api/v2/reports/tracks` → `id`. Same potential empty issue.
- Sends: POST [unlisted] → PUT [listed, body below] → GET [listed, no body] → DELETE [listed, no body]
- PUT body: `{"id": "probe-track", "start": 1613093218032, "end": 1613093237791, "tags": [], "threatLevel": 0, "displayCategory": true}`
- Ablation after matrix: PUT fields

---

### Cameras (with_tracks_only)

All camera endpoints run exclusively in the with_tracks pass. The `{id}` for all camera sub-endpoints comes from `GET /api/v2/sensors/cameras`, which in turn depends on the POST having already run.

---

**`/api/v2/sensors/cameras`**
- ⚠️ CUSTOM ORDER: `probe_order: [POST, GET, PUT, DELETE]`
- Sends: `POST [listed, body below] → GET [listed, no body] → PUT [unlisted, no body] → DELETE [unlisted, no body]`
- POST body: `{"name": 1, "controllerHostname": "172.16.0.47", "hardwareModel": "visionflex", "latitude": 40.347800, "longitude": -111.754519, "altitude": 1360.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}`
- Cleanup after matrix: `DELETE /api/v2/sensors/cameras/{id}` using `_id` from POST response
- ⚠️ STRICT ORDERING: POST is explicitly first. The camera `_id` from this POST is the source for all `{id}` camera sub-endpoints below (they all use `depends_on: "POST /api/v2/sensors/cameras"`). GET runs second to confirm the camera is visible.
- Ablation after matrix: POST top-level fields

---

**`/api/v2/sensors/cameras/follow`**
- Sends: POST [listed, `{"trackType": "track", "trackId": "probe-track-id"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields

---

**`/api/v2/sensors/cameras/go-to-lla`**
- Sends: POST [listed, `{"latitude": 40.348, "longitude": -111.758, "altitude": 1350.0}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields

---

**`/api/v2/sensors/cameras/stop-follow`**
- Sends: POST [listed, no body] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]

---

**`/api/v2/sensors/cameras/{id}/follow`**
- ⚠️ Param resolution: `GET /api/v2/sensors/cameras` → `_id`, `depends_on: POST /api/v2/sensors/cameras`. If no camera exists, fails.
- Sends: POST [listed, `{"trackType": "track", "trackId": "probe-track-id"}`] → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]
- Ablation after matrix: POST fields

---

*The following camera `{id}` action endpoints all share the same param resolution pattern:*
*⚠️ Param resolution: `GET /api/v2/sensors/cameras` → `_id`, `depends_on: POST /api/v2/sensors/cameras`*
*All send POST (with body if defined) → PUT [unlisted] → GET [unlisted] → DELETE [unlisted]*

| Endpoint | POST body |
|---|---|
| `/{id}/go-to-home` | none |
| `/{id}/go-to-lla` | `{"latitude": 40.348, "longitude": -111.758, "altitude": 1350.0}` |
| `/{id}/pixel-move` | `{"pixel": [0, 0]}` |
| `/{id}/move-camera` | `{"ptzVector": [0.0, 0.0, 0.0]}` |
| `/{id}/nudge-ptz` | `{"ptzNudge": [0.0, 0.0, 0.0]}` |
| `/{id}/reset-ptz-nudge` | none |
| `/{id}/set-home` | none |
| `/{id}/stop-follow` | none |
| `/{id}/thermal-focus` | `{"focus": 50.0}` |
| `/{id}/wiper-off` | none |
| `/{id}/wiper-on` | none |
| `/{id}/change-optical-track` | `{"offset": [0, 0]}` |
| `/{id}/clear-optical-track` | none |
| `/{id}/start-optical-calibration` | `{"radarLLA": [40.348,-111.758,1350.0], "radarRPY": [0,0,90], "radarModel": "R40"}` — ⚠️ SERVER BUG: always 500 in 5.2.3 |
| `/{id}/confirm-radar-optical-calibration` | none |
| `/{id}/deny-radar-optical-calibration` | none |
| `/{id}/stop-optical-calibration` | none |

---

**`/api/v2/sensors/cameras/{id}/optical-calibration-status`**
- ⚠️ Param resolution: `GET /api/v2/sensors/cameras` → `_id`
- Sends: POST [unlisted] → PUT [unlisted] → GET [listed, no body] → DELETE [unlisted]

---

**`/api/v2/sensors/cameras/{id}` — GET + PUT pass**
- ⚠️ SKIP: `skip_methods: [DELETE]`
- ⚠️ Param resolution: `GET /api/v2/sensors/cameras` → `_id`
- Sends: `POST [unlisted, no body] → PUT [listed, body below] → GET [listed, no body]`
- PUT body: `{"name": 1, "controllerHostname": "172.16.0.47", "latitude": 40.347801, "longitude": -111.754519, "altitude": 1361.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}`
- Ablation after matrix: PUT top-level fields

---

**`/api/v2/sensors/cameras/{id}` — DELETE pass** *(separate registry entry)*
- ⚠️ SKIP: `skip_methods: [GET, PUT, POST]` — only DELETE is sent
- ⚠️ Param resolution: `GET /api/v2/sensors/cameras` → `_id`
- Sends: `DELETE [listed, no body]`
- ⚠️ STRICT ORDERING: This entry appears last in the cameras section so DELETE only runs after all action endpoints have been probed with a live camera.

---

## Key ordering risks — summary for debugging

| What you're seeing | Most likely cause |
|---|---|
| GET /api/v2/tracks returns empty in no_containers | Expected — no live tracks. All `{id}` track endpoints will show `param_resolution_failed`. |
| GET /api/v2/tracks returns empty in with_tracks | Check the seeder wait — it polls up to 60s. If it passed (probe didn't abort), check the 20-retry loop. Status will show `429` or empty retry attempts in the console. |
| GET /api/v2/reports/tracks returns empty in with_tracks | Track reports require *completed* tracks, not just live ones. Short-lived seeder tracks may not generate reports within the probe window. |
| GET on a collection returns empty even though POST ran | POST runs first in the default order. If GET still returns empty, the most likely cause is that POST returned a non-2xx (check the `outcomes.baseline.status` in the snapshot) and the resource was never created. Check the `example_body_rejected` flag. |
| `{id}` endpoint shows `param_resolution_failed` | The dependency GET (or POST) for param resolution returned empty or failed. The dependency call is made *before* the four methods run — see "Param resolution" notes above for what each endpoint calls. |
| GET returns data in no_containers but not containers_present | containers_present only runs dronehunter endpoints. Any GET on a non-DH endpoint in containers_present would not appear at all since it's filtered out. |
