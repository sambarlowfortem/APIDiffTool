"""Request-field ablation: empirically determine which request fields are required."""

import copy
import re

from .baseline import matches_not_found
from .matrix import substitute_params, _safe_json
from .registry import get_listed_methods, extract_path_params


WRITABLE_METHODS = {"POST", "PUT", "PATCH"}


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


def run_ablation(
    client,
    base_url: str,
    registry: dict,
    matrix_results: list[dict],
    not_found_sig: dict,
    scenario: str,
    verbose: bool = True,
) -> list[dict]:
    """Run field ablation on eligible endpoints and update result entries in place.

    Returns the updated list (modified in place).
    """
    # Index matrix results by (path_template, method)
    result_index: dict[tuple, dict] = {}
    for entry in matrix_results:
        key = (entry["path"], entry["method"])
        result_index[key] = entry

    for ep in registry.get("endpoints", []):
        path_template = ep["path"]
        listed_methods = get_listed_methods(ep)
        bodies = ep.get("body") or {}

        # Resolve params
        if extract_path_params(path_template):
            from .registry import ParamResolver
            # params already resolved in matrix — grab from result
            sample_key = (path_template, listed_methods[0] if listed_methods else "GET")
            sample = result_index.get(sample_key)
            resolved_params = {}
            if sample and sample.get("_raw_resp"):
                url_used = sample["_raw_resp"].get("url", "")
                # Reconstruct resolved params from the actual URL vs template
                resolved_params = _extract_resolved_params(path_template, url_used)
        else:
            resolved_params = {}

        for method in listed_methods:
            if method not in WRITABLE_METHODS:
                continue
            body_template = bodies.get(method)
            if not body_template:
                continue

            key = (path_template, method)
            entry = result_index.get(key)
            if not entry:
                continue

            baseline_status = entry.get("outcomes", {}).get("baseline", {}).get("status", 0)
            if not (200 <= baseline_status < 300):
                # Baseline failed → flag it
                if "example_body_rejected" not in entry["registry_flags"]:
                    entry["registry_flags"].append("example_body_rejected")
                continue

            if verbose:
                print(f"  [{scenario}] ABLATE {method:6s} {path_template}")

            # Build the URL
            if resolved_params:
                path = substitute_params(path_template, resolved_params)
            else:
                path = path_template
            url = base_url.rstrip("/") + path

            request_fields = {}
            outcomes = entry.get("outcomes", {})

            # Skip ablation if body is not a dict (e.g. a JSON array — can't remove named fields)
            if not isinstance(body_template, dict):
                entry["registry_flags"].append("body_not_object_skipped_ablation")
                continue

            # Ablate each top-level field
            for field in list(body_template.keys()):
                reduced_body = {k: v for k, v in body_template.items() if k != field}
                try:
                    resp = client.request(method, url, json=reduced_body)
                    outcomes[f"missing_{field}"] = {"status": resp.status_code}
                    if 200 <= resp.status_code < 300:
                        required = False
                    elif 400 <= resp.status_code < 500:
                        required = True
                    else:
                        required = False  # ambiguous → optional
                except Exception as e:
                    outcomes[f"missing_{field}"] = {"status": 0, "error": str(e)[:80]}
                    required = False

                field_type = _infer_type(body_template[field])
                request_fields[field] = {"required": required, "type": field_type}

                # Clean up any created resource from ablation call
                _try_cleanup(client, base_url, method, resp if 'resp' in dir() else None, ep)

            entry["outcomes"] = outcomes
            entry["request_fields"] = request_fields

            # Also try to clean up the baseline-created resource
            baseline_body = entry.get("_raw_resp", {}).get("body")
            _try_cleanup(client, base_url, method, None, ep, baseline_body)

    return matrix_results


def _try_cleanup(client, base_url: str, create_method: str, resp, ep: dict, body=None):
    """Attempt to DELETE a resource created during probing."""
    if create_method != "POST":
        return
    if body is None and resp is not None:
        body = _safe_json(resp)
    if not body:
        return

    resource_id = _extract_id_from_response(body)
    if not resource_id:
        return

    path_template = ep["path"]
    # Look for a sibling endpoint with {id} that supports DELETE
    from .registry import get_listed_methods
    from .matrix import substitute_params
    id_path = path_template.rstrip("/") + "/{id}"
    # Also check registry for a matching DELETE endpoint
    # For now, just attempt DELETE on path/{id}
    url = base_url.rstrip("/") + path_template.rstrip("/") + f"/{resource_id}"
    try:
        client.request("DELETE", url)
    except Exception:
        pass


def _infer_type(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "string"


def _extract_resolved_params(template: str, url: str) -> dict:
    """Reverse-engineer resolved param values from a concrete URL vs its template."""
    import re
    params = {}
    # Build a regex from the template
    pattern = re.escape(template)
    param_names = re.findall(r'\\\{(\w+)\\\}', pattern)
    regex = re.sub(r'\\\{(\w+)\\\}', r'([^/]+)', pattern)
    m = re.match(regex, url)
    if m:
        for i, name in enumerate(param_names):
            params[name] = m.group(i + 1)
    return params
