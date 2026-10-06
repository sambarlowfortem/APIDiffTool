"""Probe matrix: send all 7 methods to every registered endpoint."""

import re
from typing import Any

from .baseline import matches_not_found
from .registry import get_all_methods, get_listed_methods, resolve_deprecated, extract_path_params
from .schema_utils import infer_schema_from_body, merge_schemas, finalize_schema


ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
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


def run_probe_matrix(
    client,
    base_url: str,
    registry: dict,
    param_resolver,
    not_found_sig: dict,
    scenario: str,
    verbose: bool = True,
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

        skip = set(ep.get("skip_methods") or [])

        for method in ALL_METHODS:
            if method in skip:
                if verbose:
                    print(f"  [{scenario}] {method:7s} {path_template}  [skipped — skip_methods]")
                continue
            if verbose:
                print(f"  [{scenario}] {method:7s} {path_template}")
            entry = probe_endpoint(
                client, base_url, ep, method, resolved, not_found_sig, scenario
            )
            results.append(entry)

    return results
