# API Diff Tool — Schema Reference

This document is the contract between Component 1 (prober) and Component 2 (diff viewer).
Neither component's code contains version- or endpoint-specific logic; everything is driven by these formats.

---

## 1. Snapshot format (schema_version "1.0")

One JSON file per probe run. File name equals `run_id`.

```json
{
  "schema_version": "1.0",
  "version": "5.2.3",
  "build": "rc1",
  "run_id": "5.2.3__rc1__20261006-162200",
  "captured_at": "2026-10-06T16:22:00Z",
  "base_url": "https://skydome.fortem",
  "registry": {
    "file": "endpoints.yaml",
    "registry_version": 1,
    "sha256": "a1b2c3..."
  },
  "format_detectors_version": "1.0",
  "not_found_signature": {
    "status": 404,
    "content_type": "application/json",
    "body_schema": {
      "error": { "type": "string", "format": "text" }
    }
  },
  "endpoints": [...]
}
```

### Top-level fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | yes | Format version, currently `"1.0"`. Major bump = breaking change. |
| `version` | string | yes | API version being probed (e.g. `"5.2.3"`). |
| `build` | string | yes | Build label within a version (e.g. `"rc1"`, `"final"`). |
| `run_id` | string | yes | `<version>__<build>__<YYYYMMDD-HHMMSS>`. Also the filename. |
| `captured_at` | string | yes | ISO 8601 UTC timestamp of probe start. |
| `base_url` | string | yes | Base URL probed (no trailing slash). |
| `registry` | object | yes | Registry metadata (see below). |
| `format_detectors_version` | string | no | Version of the format detector set. Omit in older snapshots. |
| `not_found_signature` | object | yes | What a missing route returns (see below). |
| `endpoints` | array | yes | Array of endpoint result objects (see below). |

### `registry` object

| Field | Type | Required |
|---|---|---|
| `file` | string | yes | Registry filename (e.g. `"endpoints.yaml"`). |
| `registry_version` | integer | yes | `registry_version` from the file. |
| `sha256` | string | yes | SHA-256 hex of the registry file as read. |

### `not_found_signature` object

| Field | Type | Required |
|---|---|---|
| `status` | integer | yes | HTTP status code returned for a missing route. |
| `content_type` | string | yes | Content-Type header value. |
| `body_schema` | object | yes | Field → `{ type, format }` map inferred by genson + format detectors. |

Multiple signatures recorded when different missing-route patterns return different responses; keyed by pattern name.

### Endpoint result object

```json
{
  "path": "/api/v2/zones",
  "method": "POST",
  "listed": true,
  "exists": true,
  "scenario": "containers_present",
  "deprecated": { "in": "5.1.0" },
  "request_fields": {
    "name":    { "required": true,  "type": "string" },
    "path":    { "required": true,  "type": "array" },
    "floor":   { "required": false, "type": "number" },
    "ceiling": { "required": false, "type": "number" }
  },
  "outcomes": {
    "baseline":       { "status": 201 },
    "missing_name":   { "status": 422 },
    "missing_path":   { "status": 422 },
    "missing_floor":  { "status": 201 },
    "missing_ceiling":{ "status": 201 }
  },
  "response_schema": {
    "data":    { "type": "object", "required": true },
    "_id":     { "type": "string", "format": "hex_id",             "required": true },
    "name":    { "type": "string", "format": "text",               "required": true },
    "created": { "type": "string", "format": "iso8601_datetime_z_ms", "required": true },
    "err":     { "type": "string", "format": "text",               "required": false },
    "msg":     { "type": "string", "format": "text",               "required": false }
  },
  "registry_flags": []
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `path` | string | yes | Route path, including `{param}` placeholders. |
| `method` | string | yes | HTTP method in uppercase. |
| `listed` | boolean | yes | `true` when the registry lists this method for this path. |
| `exists` | boolean | yes | `true` when the response does NOT match `not_found_signature`. |
| `scenario` | string | yes | Container state during this probe (see Scenarios). |
| `deprecated` | object | no | Copied from registry. Keys: `in` (version string), `stopped_working_in` (version string). |
| `request_fields` | object | no | Present for listed writable methods. Field → `{ required, type }`. |
| `outcomes` | object | yes | `baseline` always present; `missing_<field>` for each ablated field. Each value: `{ status }`. |
| `response_schema` | object | no | Present when `exists: true` and a JSON body was returned. Field → `{ type, format, required }`. |
| `registry_flags` | array | yes | List of flag strings. Empty when clean. |

**`exists` semantics**: `false` iff the response matches `not_found_signature`. A `404` that means "record not found on a real route" → `exists: true`.

**`response_schema` nesting**: For nested objects, keys use dot notation (e.g. `data.name`, `data.created`). Arrays record element type under `<key>[]`.

**`registry_flags` values**:
- `"example_body_rejected"` — the registry's starting body for this method returned a failure status.
- `"listed_endpoint_unavailable"` — a listed path+method returned the not-found response or 405.
- `"deprecation_stopped_working"` — registry says endpoint stopped working at/before this version, but it still works.
- `"deprecation_unexpected_failure"` — registry has no `stopped_working_in` but endpoint no longer works.

### Scenarios

| Name | Container state |
|---|---|
| `containers_present` | DroneHangar (1) + one DroneHunter up. |
| `no_containers` | DroneHangar down, all DroneHunters down. |
| `multiple_hunters` | DroneHangar (1) + all three DroneHunters up. |

Notes:
- There is at most one DroneHangar container. Scenarios never test multiple hangars.
- The same endpoint appears once per scenario (separate objects in the `endpoints` array).
- Endpoints unaffected by container state may be recorded under a single `"containers_present"` entry to avoid duplication; Component 2 compares within the same scenario name.

---

## 2. Registry format (endpoints.yaml)

```yaml
registry_version: 1        # bump on every edit
endpoints:
  - path: /api/v2/zones
    methods: [GET, POST]
    body:
      POST:
        name: "probe-zone"
        path: [[40.346,-111.797],[40.346,-111.798],[40.345,-111.798],[40.345,-111.797],[40.346,-111.797]]
        floor: 10
        ceiling: 200
        kind: "regular"
        active: true
        notes: ""
        styles: {borderDash: "solid", borderWidth: 2, fillColor: "#21E604", fillOpacity: 0.1}

  - path: /api/v2/zones/{id}
    methods: [PUT, DELETE]
    params:
      id: { from: "POST /api/v2/zones", field: "_id" }
    body:
      PUT:
        name: "probe-zone-updated"
        path: [[40.346,-111.797],[40.346,-111.798],[40.345,-111.798],[40.345,-111.797],[40.346,-111.797]]
        floor: 10
        ceiling: 200

  - path: /api/v2/map/config
    methods: [GET]
    deprecated:
      GET: { in: "5.0.0" }

  - path: /api/v2/legacy/report
    methods: [GET]
    deprecated:
      "*": { in: "3.2.0", stopped_working_in: "4.0.0" }
    removed_from_docs: "4.0.0"
```

### Registry field table

| Field | Required | Purpose |
|---|---|---|
| `registry_version` | yes | Integer. Bump on every edit. Stored in every snapshot. |
| `path` | yes | Route path with `{param}` placeholders. |
| `methods` | yes | HTTP methods the docs list. These get full body + ablation testing. |
| `params` | when path has placeholders | Map of param name → `{ from: "<METHOD> <path>", field: "<response_field>" }` or `{ value: "<literal>" }`. |
| `body` | for each writable method | Known-good starting request body for ablation. Keyed by method. |
| `deprecated` | no | Map of method (or `"*"`) → `{ in: "<version>" }` and optionally `{ stopped_working_in: "<version>" }`. |
| `removed_from_docs` | no | Version string when the endpoint left the docs. Informational only. |
| `skip_methods` | no | List of HTTP methods the prober must NOT send to this endpoint (e.g. `[POST]` on restart/shutdown endpoints whose side effect is real and destructive). The method is not probed at all; it does not appear in the snapshot. |

### Registry rules
- **Never delete an entry.** When an endpoint leaves the docs, add `removed_from_docs` instead.
- **Bump `registry_version` on every edit.**
- The prober sends all seven HTTP methods (GET POST PUT PATCH DELETE HEAD OPTIONS) to every path, even unlisted ones; listed methods additionally get body + ablation.
- Keep in git next to the prober.

---

## 3. JSON Schema for registry validation

See `endpoints_schema.json` alongside this file. The prober validates `endpoints.yaml` against it and refuses to run on a malformed registry.

---

## 4. Format-name vocabulary

Format names are opaque labels to Component 2. Adding a new detector never requires a viewer change. Bump `format_detectors_version` in snapshots whenever the detector set changes.

### Date-times

| Name | Description |
|---|---|
| `iso8601_datetime_z` | `2026-10-06T16:22:00Z` — UTC, no fractional seconds |
| `iso8601_datetime_z_ms` | `2026-10-06T16:22:00.123Z` — UTC, milliseconds |
| `iso8601_datetime_z_us` | UTC, microseconds |
| `iso8601_datetime_offset` | `2026-10-06T16:22:00+05:00` — with numeric offset |
| `iso8601_datetime_offset_ms` | With numeric offset and milliseconds |
| `iso8601_datetime_naive` | No timezone designator |
| `rfc2822_datetime` | `Tue, 06 Oct 2026 16:22:00 +0000` |
| `http_date` | `Tue, 06 Oct 2026 16:22:00 GMT` |

### Dates and times

| Name | Description |
|---|---|
| `iso8601_date` | `2026-10-06` |
| `us_date_mdy` | `10/06/2026` — unambiguous month-first |
| `day_date_dmy` | `06/10/2026` — unambiguous day-first |
| `slash_date_ambiguous` | `01/02/2026` — day ≤ 12, order unknown |
| `time_hms` | `16:22:00` |
| `time_hms_ms` | `16:22:00.123` |
| `iso8601_duration` | `PT5M`, `P1DT2H` |

### Epoch time

| Name | Description |
|---|---|
| `epoch_seconds` | Unix seconds as number (plausible year range check) |
| `epoch_milliseconds` | Unix milliseconds as number |
| `epoch_microseconds` | Unix microseconds as number |
| `epoch_seconds_string` | Unix seconds encoded as string |
| `epoch_milliseconds_string` | Unix milliseconds encoded as string |

### Identifiers

| Name | Description |
|---|---|
| `uuid_lower` | `550e8400-e29b-41d4-a716-446655440000` |
| `uuid_upper` | `550E8400-E29B-41D4-A716-446655440000` |
| `uuid_lower_no_hyphens` | Without hyphens, lowercase |
| `uuid_upper_no_hyphens` | Without hyphens, uppercase |
| `hex_id` | Hex string (not UUID), e.g. MongoDB ObjectId `6a8c6eb1a548d202ede14418` |
| `base64` | Standard base64 encoded string |
| `integer_as_string` | A decimal integer encoded as string |

### Network

| Name | Description |
|---|---|
| `email` | Email address |
| `url_absolute` | Absolute URL starting with http/https |
| `url_relative` | Relative URL (starts with `/`) |
| `ipv4` | IPv4 address |
| `ipv6` | IPv6 address |
| `mac_address` | MAC address |

### Numbers

| Name | Description |
|---|---|
| `integer` | Whole number (JSON number type) |
| `decimal` | Floating-point (JSON number type) |
| `number_as_string` | Any numeric string that isn't integer_as_string |
| `boolean_as_string_true_false` | The strings `"true"` or `"false"` |
| `boolean_as_string_01` | The strings `"0"` or `"1"` |

### Enum-like strings

| Name | Description |
|---|---|
| `enum_upper_snake` | `UPPER_SNAKE_CASE` |
| `enum_lower_snake` | `lower_snake_case` |
| `enum_camel` | `camelCase` |
| `enum_kebab` | `kebab-case` |
| `enum_title` | `Title Case` |

### Empties / nulls

| Name | Description |
|---|---|
| `null_value` | JSON null |
| `empty_string` | `""` |
| `empty_array` | `[]` |
| `empty_object` | `{}` |

### Catch-all

| Name | Description |
|---|---|
| `text` | Free-form string that matched no other detector |
| `shape:<pattern>` | Consistent short string pattern, e.g. `shape:AAA-9999` (A=letter, 9=digit). Used when no named format matches and the shape is consistent across samples. |
| `mixed:<f1>,<f2>` | Multiple formats observed for the same field across samples |
| `ambiguous` | Could not be classified (e.g. `slash_date_ambiguous`) — recorded explicitly |
| `unknown` | Type is not inferrable (e.g. always null or empty array) |

---

## 5. Forward compatibility rules

### Viewer rules
- Ignore unknown top-level and nested fields in snapshots.
- Same major `schema_version` → load and compare normally.
- Newer major `schema_version` → try to load, show a banner that the viewer may be out of date.
- Missing optional fields → treat as absent (no error).
- Scenarios in one run that are absent from the other → flag as "scenario present in only one run."
- Format names are opaque labels; unknown names display as-is.

### Snapshot format rules
- New optional fields → additive change, bump minor `schema_version`.
- Renamed or removed fields → breaking change, bump major `schema_version`, update viewer in same commit.
- `run_id` = filename (no `.json` suffix in the field; file has `.json` extension).
