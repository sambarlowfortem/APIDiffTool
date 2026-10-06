#!/usr/bin/env python3
"""probe.py — API Diff Tool prober CLI.

Usage:
  python3 probe/probe.py --version 5.2.3 [--build rc1] [--base-url https://skydome.fortem] [--out results/]
"""

import argparse
import copy
import hashlib
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python3 probe/probe.py` from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from probe.auth import AuthManager, AuthError
from probe.baseline import record_not_found_baseline, matches_not_found
from probe.containers import ContainerManager, SCENARIOS
from probe.http_client import HttpClient
from probe.matrix import run_probe_matrix
from probe.ablation import run_ablation
from probe.registry import load_registry, RegistryError, ParamResolver
from probe.report import generate_report
from probe.formats import FORMAT_DETECTORS_VERSION


def load_config(config_path: str = "config.json") -> dict:
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


def parse_args():
    p = argparse.ArgumentParser(description="API Diff Tool — probe a running API instance")
    p.add_argument("--version", required=True, help="API version string (e.g. 5.2.3)")
    p.add_argument("--build", default=None, help="Build label (e.g. rc1, final). Prompted if not given.")
    p.add_argument("--base-url", default=None, help="Base URL of the API (e.g. https://skydome.fortem)")
    p.add_argument("--out", default="results", help="Output directory (default: results/)")
    p.add_argument("--registry", default="endpoints.yaml", help="Path to endpoints.yaml")
    p.add_argument("--schema", default="endpoints_schema.json", help="Path to registry JSON Schema")
    p.add_argument("--email", default=None, help="Login email")
    p.add_argument("--password", default=None, help="Login password")
    p.add_argument("--settle-wait", type=int, default=20, help="Seconds to wait after container state change (default: 20)")
    p.add_argument("--redact", default="", help="Comma-separated field names to mask in reports")
    p.add_argument("--scenarios", default="no_containers,containers_present,multiple_hunters",
                   help="Comma-separated scenarios to run (default: all three)")
    p.add_argument("--skip-containers", action="store_true",
                   help="Skip container management (run a single probe in current state)")
    p.add_argument("--delay", type=float, default=0.0,
                   help="Seconds to sleep between requests (default: 0). Use 0.1-0.5 to reduce server load.")
    p.add_argument("--verbose", action="store_true", default=True)
    return p.parse_args()


def main():
    args = parse_args()

    # Load config.json for defaults
    cfg = load_config()

    base_url = args.base_url or cfg.get("sd_url", "").rstrip("/")
    if not base_url:
        base_url = input("Base URL [https://skydome.fortem]: ").strip() or "https://skydome.fortem"

    email = args.email or cfg.get("email", "")
    if not email:
        email = input("Email: ").strip()

    password = args.password or cfg.get("password", "")
    if not password:
        import getpass
        password = getpass.getpass("Password: ")

    build = args.build
    if not build:
        build = input("Build label (e.g. rc1, final): ").strip() or "run"

    redact_fields = set(f.strip() for f in args.redact.split(",") if f.strip())
    scenarios_to_run = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    # Validate scenario names
    for s in scenarios_to_run:
        if s not in SCENARIOS:
            print(f"ERROR: Unknown scenario '{s}'. Valid: {', '.join(SCENARIOS)}")
            sys.exit(1)

    # Build run_id and output paths
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"{args.version}__{build}__{timestamp}"
    out_dir = os.path.join(args.out, args.version)
    os.makedirs(out_dir, exist_ok=True)
    snapshot_path = os.path.join(out_dir, f"{run_id}.json")
    report_path = os.path.join(out_dir, f"{run_id}.report.html")

    print(f"\n=== API Diff Tool Prober ===")
    print(f"Version : {args.version}")
    print(f"Build   : {build}")
    print(f"Run ID  : {run_id}")
    print(f"Base URL: {base_url}")
    print(f"Output  : {snapshot_path}")
    print()

    # Load and validate registry
    print("Loading registry...")
    try:
        registry = load_registry(args.registry, args.schema)
    except RegistryError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    print(f"Registry v{registry['registry_version']} loaded ({len(registry.get('endpoints', []))} endpoints)")

    # Auth
    print("Authenticating...")
    auth = AuthManager(base_url, email, password)
    try:
        auth.login()
    except AuthError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    auth.start_auto_refresh()
    print("Authentication OK")

    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    client = HttpClient(auth, delay=args.delay)

    # Not-found baseline
    print("\nRecording not-found baseline...")
    not_found_sig = record_not_found_baseline(client, base_url)
    print(f"Not-found signature: status={_sig_status(not_found_sig)}")

    # Container management
    containers = ContainerManager()
    if not args.skip_containers and containers.client:
        containers.save_initial_state()

    # Param resolver (shared, caches across scenarios)
    def http_fn(method, url, **kwargs):
        return client.request(method, url, **kwargs)

    param_resolver = ParamResolver(registry, http_fn)

    all_endpoint_results = []

    try:
        if args.skip_containers:
            # Run once with whatever state we're in
            print("\n--- Single probe run (no container management) ---")
            scenario = "containers_present"
            results = run_probe_matrix(
                client, base_url, registry, param_resolver, not_found_sig, scenario, args.verbose
            )
            results = run_ablation(
                client, base_url, registry, results, not_found_sig, scenario, args.verbose
            )
            all_endpoint_results.extend(results)
        else:
            for scenario in scenarios_to_run:
                if containers.client:
                    containers.apply_scenario(scenario, args.settle_wait)
                    expected_hangar = 1 if scenario != "no_containers" else 0
                    expected_hunters = {"no_containers": 0, "containers_present": 1, "multiple_hunters": 3}[scenario]
                    containers.wait_for_settle(expected_hangar, expected_hunters, client, base_url, args.settle_wait)
                else:
                    print(f"\n--- Scenario: {scenario} (Docker unavailable, skipping container changes) ---")

                # Reset param resolver cache between scenarios (state may differ)
                param_resolver = ParamResolver(registry, http_fn)

                print(f"\nProbing matrix for scenario: {scenario}")
                results = run_probe_matrix(
                    client, base_url, registry, param_resolver, not_found_sig, scenario, args.verbose
                )
                print(f"\nRunning ablation for scenario: {scenario}")
                results = run_ablation(
                    client, base_url, registry, results, not_found_sig, scenario, args.verbose
                )
                all_endpoint_results.extend(results)

    finally:
        if not args.skip_containers and containers.client:
            print("\nRestoring container state...")
            containers.restore_initial_state()

    auth.stop_auto_refresh()
    client.close()

    # Build snapshot
    snapshot = _build_snapshot(
        version=args.version,
        build=build,
        run_id=run_id,
        captured_at=captured_at,
        base_url=base_url,
        registry=registry,
        not_found_sig=not_found_sig,
        endpoint_results=all_endpoint_results,
    )

    # Write snapshot JSON (strip internal _raw_resp before writing)
    clean_snapshot = _strip_internal_fields(snapshot)
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(clean_snapshot, f, indent=2, sort_keys=True)
    print(f"\nSnapshot written: {snapshot_path}")

    # Write HTML report
    generate_report(snapshot, registry, redact_fields=redact_fields, output_path=report_path)
    print(f"Report written  : {report_path}")

    print("\nDone.")


def _sig_status(sig: dict) -> str:
    if "status" in sig:
        return str(sig["status"])
    return str({k: v.get("status") for k, v in sig.items()})


def _build_snapshot(
    version, build, run_id, captured_at, base_url,
    registry, not_found_sig, endpoint_results
) -> dict:
    reg_sha = registry.get("_sha256", "")
    reg_path = registry.get("_yaml_path", "endpoints.yaml")

    # Copy deprecation from registry onto endpoint results
    dep_map = {}
    for ep in registry.get("endpoints", []):
        from probe.registry import resolve_deprecated
        for method in ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]:
            dep = resolve_deprecated(ep, method)
            if dep:
                dep_map[(ep["path"], method)] = dep

    endpoints_out = []
    for entry in endpoint_results:
        e = copy.deepcopy(entry)
        # Remove internal fields
        e.pop("_raw_resp", None)
        # Apply deprecation from registry
        key = (e.get("path"), e.get("method"))
        if key in dep_map and "deprecated" not in e:
            e["deprecated"] = dep_map[key]
        # Sort registry_flags
        e["registry_flags"] = sorted(set(e.get("registry_flags", [])))
        endpoints_out.append(e)

    return {
        "schema_version": "1.0",
        "version": version,
        "build": build,
        "run_id": run_id,
        "captured_at": captured_at,
        "base_url": base_url,
        "registry": {
            "file": os.path.basename(reg_path),
            "registry_version": registry["registry_version"],
            "sha256": reg_sha,
        },
        "format_detectors_version": FORMAT_DETECTORS_VERSION,
        "not_found_signature": not_found_sig,
        "endpoints": endpoints_out,
        # Keep _raw_resp in memory for report generation, stripped before JSON write
        "_endpoint_results_with_raw": endpoint_results,
    }


def _strip_internal_fields(snapshot: dict) -> dict:
    clean = {k: v for k, v in snapshot.items() if not k.startswith("_")}
    return clean


if __name__ == "__main__":
    main()
