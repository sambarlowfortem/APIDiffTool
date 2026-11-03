"""Probe matrix: send GET, POST, PUT, DELETE to every registered endpoint."""

import random
import re
import time
from typing import Any

from .baseline import matches_not_found
from .registry import get_all_methods, get_listed_methods, resolve_deprecated, extract_path_params
from .schema_utils import infer_schema_from_body, merge_schemas, finalize_schema


ALL_METHODS = ["POST", "PUT", "GET", "DELETE"]
WRITABLE_METHODS = {"POST", "PUT"}


def substitute_params(path_template: str, resolved: dict) -> str:
    def _replace(m):
        name = m.group(1)
        return str(resolved.get(name, f"{{{name}}}"))
    return re.sub(r'\{(\w+)\}', _replace, path_template)


def probe_endpoint(
    client,
    base_url: str,
    endpoint: dict,
    method: str,
    resolved_params: dict | None,
    not_found_sig: dict,
    scenario: str,
) -> dict:
    """Probe a single endpoint+method and return the result entry dict."""
    path_template = endpoint["path"]
    listed_methods = get_listed_methods(endpoint)
    listed = method in listed_methods

    flags = []

    # Resolve path params
    if "{" in path_template:
        if not resolved_params:
            flags.append("param_resolution_failed")
            return {
                "path": path_template,
                "method": method,
                "listed": listed,
                "exists": False,
                "scenario": scenario,
                "outcomes": {"baseline": {"status": 0, "error": "param_resolution_failed"}},
                "registry_flags": flags,
            }
        path = substitute_params(path_template, resolved_params)
    else:
        path = path_template

    url = base_url.rstrip("/") + path

    # Build request kwargs
    body = None
    if listed and method in WRITABLE_METHODS:
        body = (endpoint.get("body") or {}).get(method)

    kwargs = {}
    if body is not None:
        kwargs["json"] = body
    if method == "GET":
        qp = (endpoint.get("query_params") or {}).get(method)
        if qp:
            kwargs["params"] = qp

    # Send baseline
    try:
        resp = client.request(method, url, **kwargs)
    except Exception as e:
        flags.append("request_error")
        return {
            "path": path_template,
            "method": method,
            "listed": listed,
            "exists": False,
            "scenario": scenario,
            "outcomes": {"baseline": {"status": 0, "error": str(e)[:100]}},
            "registry_flags": flags,
        }

    exists = not matches_not_found(resp, not_found_sig)
    outcomes = {"baseline": {"status": resp.status_code}}

    # Parse body once; sanitize volatile fields so transient data doesn't
    # produce schema diffs between runs.
    raw_body = _safe_json(resp)
    if path_template == "/api/v2/tracks" and scenario == "with_tracks":
        raw_body = _sanitize_track_newpoints(raw_body)
    if path_template == "/api/v2/dronehunters":
        raw_body = _sanitize_dronehunter_health(raw_body)

    # Infer response schema
    response_schema = None
    if exists and resp.status_code < 300:
        try:
            exhaust = "/system/notifications" in path_template
            schema = infer_schema_from_body(raw_body, exhaust_arrays=exhaust)
            if schema:
                # Mark all fields as required initially (single sample)
                for info in schema.values():
                    info["required"] = True
                # Apply per-endpoint field overrides (forces type; strips format unless specified)
                overrides = endpoint.get("response_field_overrides") or {}
                for field_key, override_info in overrides.items():
                    if field_key in schema:
                        entry = dict(schema[field_key])
                        if "type" in override_info:
                            entry["type"] = override_info["type"]
                        # Remove format unless the override explicitly provides one
                        if "format" in override_info:
                            fmt = override_info["format"]
                            if fmt is None:
                                entry.pop("format", None)
                            else:
                                entry["format"] = fmt
                        else:
                            entry.pop("format", None)
                        schema[field_key] = entry
                response_schema = schema

                if method == "POST":
                    excludes = endpoint.get("post_schema_excludes") or []
                    if excludes:
                        response_schema = {
                            k: v for k, v in response_schema.items()
                            if not any(
                                k == exc or k.startswith(exc + ".") or k.startswith(exc + "[")
                                for exc in excludes
                            )
                        }
        except Exception:
            pass

    # Registry flags for listed endpoints
    if listed:
        dep = resolve_deprecated(endpoint, method)
        if not exists or resp.status_code == 405:
            flags.append("listed_endpoint_unavailable")
        elif dep and dep.get("stopped_working_in"):
            # Endpoint should have stopped working, but it works
            flags.append("deprecation_stopped_working")
        if dep and not dep.get("stopped_working_in") and not exists:
            flags.append("deprecation_unexpected_failure")

    entry = {
        "path": path_template,
        "method": method,
        "listed": listed,
        "exists": exists,
        "scenario": scenario,
        "outcomes": outcomes,
        "registry_flags": flags,
    }

    dep_info = resolve_deprecated(endpoint, method)
    if dep_info:
        entry["deprecated"] = dep_info

    if response_schema:
        entry["response_schema"] = response_schema

    # Store raw response for ablation and report
    entry["_raw_resp"] = {
        "status": resp.status_code,
        "body": raw_body,
        "url": url,
    }

    return entry


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return None


def _extract_id_from_response(body, extra_id_field: str | None = None) -> str | None:
    """Try to find an ID field in a response body for cleanup."""
    if not isinstance(body, dict):
        return None
    candidates = ([extra_id_field] if extra_id_field else []) + ["_id", "id", "featureId"]
    for key in candidates:
        val = body.get(key)
        if val:
            return str(val)
        data = body.get("data")
        if isinstance(data, dict):
            val = data.get(key)
            if val:
                return str(val)
    return None


def _cleanup_matrix_post(client, base_url: str, ep: dict, ep_results: list[dict]):
    """Best-effort DELETE of the resource created by the matrix POST probe."""
    if ep.get("no_auto_cleanup"):
        return
    post_entry = next(
        (e for e in ep_results if e.get("method") == "POST" and e.get("_raw_resp")),
        None,
    )
    if not post_entry:
        return
    body = post_entry["_raw_resp"].get("body")
    if not body:
        return
    resource_id = _extract_id_from_response(body, ep.get("cleanup_id_field"))
    if not resource_id:
        return
    path_template = ep["path"]
    # Only attempt cleanup for collection endpoints (no path params) to avoid
    # constructing nonsense URLs for action endpoints like /{id}/follow.
    if "{" in path_template:
        return
    url = base_url.rstrip("/") + path_template.rstrip("/") + f"/{resource_id}"
    try:
        client.request("DELETE", url)
    except Exception:
        pass


def _sanitize_track_newpoints(body) -> dict:
    """Replace non-empty newPoints arrays with [] in track entries.

    newPoints content varies per-probe (live position updates) and would produce
    false schema diffs between runs. The array's existence and type are recorded;
    its contents are not.
    """
    if not isinstance(body, dict):
        return body
    data = body.get("data")
    if not isinstance(data, dict):
        return body
    sanitized = {}
    for track_id, track in data.items():
        if isinstance(track, dict) and track.get("newPoints"):
            track = {**track, "newPoints": []}
        sanitized[track_id] = track
    return {**body, "data": sanitized}


def _sanitize_dronehunter_health(body) -> dict:
    """Replace health dict contents with {} in dronehunter entries.

    health varies per-probe (assignment, condition, etc.) and would produce
    false schema diffs between runs. The field's existence and dict type are
    recorded; its contents are not.
    """
    if not isinstance(body, dict):
        return body
    data = body.get("data")
    if not isinstance(data, list):
        return body
    sanitized = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("health"), dict):
            item = {**item, "health": {}}
        sanitized.append(item)
    return {**body, "data": sanitized}


def _field_path_matches(obj, parts: list[str], expected_value) -> bool:
    """Navigate a dot-split path ([] suffix fans out over arrays) and return True if any leaf == expected_value."""
    if not parts:
        return obj == expected_value
    part = parts[0]
    rest = parts[1:]
    if part.endswith("[]"):
        key = part[:-2]
        arr = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(arr, list):
            return any(_field_path_matches(item, rest, expected_value) for item in arr)
        return False
    if isinstance(obj, dict) and part in obj:
        return _field_path_matches(obj[part], rest, expected_value)
    return False


def _check_get_retry_while(entry: dict, conditions: list[dict]) -> bool:
    """Return True if any get_retry_while condition is satisfied in the entry's response body."""
    raw = entry.get("_raw_resp", {})
    body = raw.get("body")
    if not isinstance(body, dict):
        return False
    for cond in conditions:
        parts = cond.get("field", "").split(".")
        if _field_path_matches(body, parts, cond.get("value")):
            return True
    return False


def _is_empty_response(entry: dict) -> bool:
    """Return True if the entry's response body is None, [], {}, or has an empty data collection."""
    raw = entry.get("_raw_resp", {})
    body = raw.get("body")
    if body is None:
        return True
    if isinstance(body, (list, dict)) and len(body) == 0:
        return True
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, (dict, list)) and len(data) == 0:
            return True
    return False


def _should_retry_get(entry: dict, post_succeeded: bool = False) -> bool:
    """Return True if this GET should be retried.

    For /api/v2/tracks: retries on empty response or 429 (rate-limited at 1Hz).
    For any other endpoint where the preceding POST succeeded: retries on empty
    data, to handle server-side list caches that haven't been invalidated yet.
    """
    path = entry.get("path", "")
    raw = entry.get("_raw_resp", {})
    status = raw.get("status", 0)

    if path == "/api/v2/tracks":
        if status == 429:
            return True  # rate-limited; retry after mandatory 1s sleep in the retry loop
        return _is_empty_response(entry)

    if post_succeeded:
        return _is_empty_response(entry)

    return False


def run_probe_matrix(
    client,
    base_url: str,
    registry: dict,
    param_resolver,
    not_found_sig: dict,
    scenario: str,
    verbose: bool = True,
    retry_empty_get_max: int = 0,
    retry_empty_get_delay: int = 3,
) -> list[dict]:
    """Run GET, POST, PUT, DELETE against every endpoint in the registry.

    Returns a list of endpoint result dicts (one per path×method).
    """
    results = []
    endpoints = registry.get("endpoints", [])

    for ep in endpoints:
        path_template = ep["path"]
        # Resolve params once per endpoint (shared across methods)
        if extract_path_params(path_template):
            resolved = param_resolver.resolve(ep, base_url)
        else:
            resolved = {}

        # Ensure prerequisites exist before probing (e.g. a resource the body references)
        for pre in ep.get("pre_create", []):
            try:
                pre_path = pre["path"]
                if pre.get("use_resolved_params") and resolved:
                    pre_path = substitute_params(pre_path, resolved)
                pre_url = base_url.rstrip("/") + pre_path
                pre_body = pre.get("body")
                if pre_body:
                    client.request(pre["method"], pre_url, json=pre_body)
                else:
                    client.request(pre["method"], pre_url)
            except Exception:
                pass

        skip = set(ep.get("skip_methods") or [])
        probe_order = ep.get("probe_order") or ALL_METHODS
        # Append any ALL_METHODS entries not already in probe_order so nothing is silently dropped
        seen = set(probe_order)
        effective_order = list(probe_order) + [m for m in ALL_METHODS if m not in seen]
        ep_results = []
        post_succeeded_for_ep = False

        for method in effective_order:
            if method in skip:
                if verbose:
                    print(f"  [{scenario}] {method:7s} {path_template}  [skipped — skip_methods]")
                continue
            if verbose:
                print(f"  [{scenario}] {method:7s} {path_template}")
            entry = probe_endpoint(
                client, base_url, ep, method, resolved, not_found_sig, scenario
            )

            if method == "POST" and entry.get("_raw_resp", {}).get("status", 0) in range(200, 300):
                post_succeeded_for_ep = True

            if retry_empty_get_max > 0 and method == "GET":
                get_retry_while_conds = ep.get("get_retry_while") or []
                is_std = _should_retry_get(entry, post_succeeded=post_succeeded_for_ep)
                is_incomplete = bool(get_retry_while_conds) and _check_get_retry_while(entry, get_retry_while_conds)

                if is_std or is_incomplete:
                    for attempt in range(1, retry_empty_get_max + 1):
                        raw_status = entry.get("_raw_resp", {}).get("status", 0)
                        if is_incomplete:
                            reason = "incomplete field"
                            time.sleep(2)
                        elif path_template == "/api/v2/tracks":
                            # /api/v2/tracks is rate-limited at 1Hz; avoid phase-locking with the data window.
                            reason = "429 rate-limited" if raw_status == 429 else "empty response"
                            time.sleep(random.uniform(1.0, 2.0))
                        else:
                            reason = "empty response"
                            if retry_empty_get_delay > 0:
                                time.sleep(retry_empty_get_delay)
                        if verbose:
                            print(f"    [{scenario}] GET {path_template} — {reason}, retrying (attempt {attempt}/{retry_empty_get_max})")
                        entry = probe_endpoint(
                            client, base_url, ep, method, resolved, not_found_sig, scenario
                        )
                        is_std = _should_retry_get(entry, post_succeeded=post_succeeded_for_ep)
                        is_incomplete = bool(get_retry_while_conds) and _check_get_retry_while(entry, get_retry_while_conds)
                        if not is_std and not is_incomplete:
                            if verbose:
                                print(f"    [{scenario}] GET {path_template} — got data on attempt {attempt}")
                            break

            ep_results.append(entry)

        results.extend(ep_results)

        # Best-effort cleanup of POST-created resource (after GET has already run)
        _cleanup_matrix_post(client, base_url, ep, ep_results)

    return results
