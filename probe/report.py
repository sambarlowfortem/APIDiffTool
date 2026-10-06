"""HTML run report generator."""

import copy
import json
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _truncate_body(body, max_array=3, max_str=200):
    """Truncate example bodies: cap arrays, truncate strings."""
    if isinstance(body, dict):
        return {k: _truncate_body(v, max_array, max_str) for k, v in body.items()}
    if isinstance(body, list):
        truncated = [_truncate_body(v, max_array, max_str) for v in body[:max_array]]
        if len(body) > max_array:
            truncated.append(f"... ({len(body) - max_array} more items)")
        return truncated
    if isinstance(body, str) and len(body) > max_str:
        return body[:max_str] + "..."
    return body


def _redact_body(body, redact_fields: set):
    if not redact_fields:
        return body
    if isinstance(body, dict):
        return {
            k: "[REDACTED]" if k in redact_fields else _redact_body(v, redact_fields)
            for k, v in body.items()
        }
    if isinstance(body, list):
        return [_redact_body(v, redact_fields) for v in body]
    return body


def generate_report(
    snapshot: dict,
    registry: dict,
    redact_fields: set = None,
    output_path: str = None,
) -> str:
    """Generate the HTML run report and return it as a string."""
    redact_fields = redact_fields or set()

    # Group endpoint results by (path, method), keeping only 2xx baseline
    working = []
    for ep in snapshot.get("endpoints", []):
        baseline_status = ep.get("outcomes", {}).get("baseline", {}).get("status", 0)
        if 200 <= baseline_status < 300:
            working.append(ep)

    # Group by path
    from collections import defaultdict
    by_path = defaultdict(list)
    for ep in working:
        by_path[ep["path"]].append(ep)

    # Build registry body lookup
    reg_bodies = {}
    for reg_ep in registry.get("endpoints", []):
        path = reg_ep["path"]
        for method, body in (reg_ep.get("body") or {}).items():
            reg_bodies[(path, method)] = body

    # Prepare data for template
    groups = []
    for path in sorted(by_path.keys()):
        entries = by_path[path]
        # Group by method, then by scenario
        method_map = defaultdict(list)
        for ep in entries:
            method_map[ep["method"]].append(ep)

        methods_data = []
        for method in sorted(method_map.keys()):
            scenarios_data = []
            for ep in method_map[method]:
                raw_resp = ep.get("_raw_resp") or {}
                example_body = raw_resp.get("body")
                if example_body:
                    example_body = _truncate_body(_redact_body(example_body, redact_fields))

                reg_body = reg_bodies.get((path, method))
                if reg_body:
                    reg_body = _redact_body(reg_body, redact_fields)

                scenarios_data.append({
                    "scenario": ep.get("scenario", ""),
                    "status": ep.get("outcomes", {}).get("baseline", {}).get("status"),
                    "deprecated": ep.get("deprecated"),
                    "request_fields": ep.get("request_fields") or {},
                    "response_schema": ep.get("response_schema") or {},
                    "registry_flags": ep.get("registry_flags") or [],
                    "registry_body": json.dumps(reg_body, indent=2) if reg_body else None,
                    "example_response": json.dumps(example_body, indent=2) if example_body else None,
                })

            methods_data.append({
                "method": method,
                "scenarios": scenarios_data,
                # Differences across scenarios
                "has_scenario_diff": _has_scenario_diff(scenarios_data),
            })

        groups.append({"path": path, "methods": methods_data})

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html.j2")

    html = template.render(
        snapshot=snapshot,
        groups=groups,
        working_count=len(working),
    )

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    return html


def _has_scenario_diff(scenarios_data: list) -> bool:
    if len(scenarios_data) <= 1:
        return False
    statuses = {s["status"] for s in scenarios_data}
    if len(statuses) > 1:
        return True
    # Check if response schemas differ
    schemas = [json.dumps(s["response_schema"], sort_keys=True) for s in scenarios_data]
    return len(set(schemas)) > 1
