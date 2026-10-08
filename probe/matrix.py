"""Probe matrix: send all 7 methods to every registered endpoint."""

import re
import time
from typing import Any

from .baseline import matches_not_found
from .registry import get_all_methods, get_listed_methods, resolve_deprecated, extract_path_params
from .schema_utils import infer_schema_from_body, merge_schemas, finalize_schema


ALL_METHODS = ["POST", "PUT", "PATCH", "GET", "DELETE", "HEAD", "OPTIONS"]
WRITABLE_METHODS = {"POST", "PUT", "PATCH"}


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

    # Infer response schema
    response_schema = None
    if exists and resp.status_code < 300:
        try:
            body_data = resp.json()
            schema = infer_schema_from_body(body_data)
            if schema:
                # Mark all fields as required initially (single sample)
                for info in schema.values():
                    info["required"] = True
                response_schema = schema
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
        "body": _safe_json(resp),
        "url": url,
    }

    return entry


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return None


def _extract_id_from_response(body) -> str | None:
    """Try to find an ID field in a response body for cleanup."""
    if not isinstance(body, dict):
        return None
    for key in ("_id", "id", "featureId"):
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
    post_entry = next(
        (e for e in ep_results if e.get("method") == "POST" and e.get("_raw_resp")),
        None,
    )
    if not post_entry:
        return
    body = post_entry["_raw_resp"].get("body")
    if not body:
        return
    resource_id = _extract_id_from_response(body)
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


def _is_empty_response(entry: dict) -> bool:
    """Return True if the entry's response body is None, [], or {}."""
    raw = entry.get("_raw_resp", {})
    body = raw.get("body")
    if body is None:
        return True
    if isinstance(body, (list, dict)) and len(body) == 0:
        return True
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
    """Run all 7 methods against every endpoint in the registry.

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

            if (
                retry_empty_get_max > 0
                and method == "GET"
                and entry.get("exists")
                and _is_empty_response(entry)
            ):
                for attempt in range(1, retry_empty_get_max + 1):
                    if verbose:
                        print(f"    [{scenario}] GET {path_template} — empty response, retrying in {retry_empty_get_delay}s (attempt {attempt}/{retry_empty_get_max})")
                    time.sleep(retry_empty_get_delay)
                    entry = probe_endpoint(
                        client, base_url, ep, method, resolved, not_found_sig, scenario
                    )
                    if not _is_empty_response(entry):
                        if verbose:
                            print(f"    [{scenario}] GET {path_template} — got data on attempt {attempt}")
                        break

            ep_results.append(entry)

        results.extend(ep_results)

        # Best-effort cleanup of POST-created resource (after GET has already run)
        _cleanup_matrix_post(client, base_url, ep, ep_results)

    return results
