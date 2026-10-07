#!/usr/bin/env python3
"""Debug script: exercise the ContainerManager exactly as the prober does.

Runs the containers_present scenario (dronehangar + dronehunter-1 up,
dronehunter-2/3 down), waits for the settle period, then restores the
original state. Optionally checks the SkyDome API counts if config.json
is available.

Usage:
  python3 scripts/debug_containers.py
  python3 scripts/debug_containers.py --scenario multiple_hunters
  python3 scripts/debug_containers.py --no-api       # skip API settle check
  python3 scripts/debug_containers.py --settle-wait 30
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import docker
import docker.errors

from probe.containers import ContainerManager, SCENARIOS


def parse_args():
    p = argparse.ArgumentParser(description="Debug: start/stop containers via ContainerManager")
    p.add_argument(
        "--scenario",
        default="containers_present",
        choices=list(SCENARIOS),
        help="Scenario to apply (default: containers_present)",
    )
    p.add_argument(
        "--settle-wait",
        type=int,
        default=20,
        help="Seconds to wait for containers to settle (default: 20)",
    )
    p.add_argument(
        "--no-api",
        action="store_true",
        help="Skip the SkyDome API settle check (container state only)",
    )
    p.add_argument(
        "--config",
        default="config.json",
        help="Path to config.json (default: config.json)",
    )
    return p.parse_args()


def print_container_states(client):
    from probe.containers import CONTAINER_NAMES
    print("\n  Container states:")
    for name in CONTAINER_NAMES:
        try:
            c = client.containers.get(name)
            c.reload()
            print(f"    {name:20s}  {c.status}")
        except docker.errors.NotFound:
            print(f"    {name:20s}  (not found)")
        except Exception as e:
            print(f"    {name:20s}  ERROR: {e}")


def check_api_counts(base_url, email, password, scenario, settle_wait):
    print("\n  Checking SkyDome API counts...")
    try:
        from probe.auth import AuthManager, AuthError
        from probe.http_client import HttpClient
        from probe.containers import _check_count

        auth = AuthManager(base_url, email, password)
        auth.login()
        client = HttpClient(auth)

        expected_hangar = 1 if scenario != "no_containers" else 0
        expected_hunters = {"containers_present": 1, "multiple_hunters": 3}.get(scenario, 0)

        deadline = time.time() + settle_wait
        settled = False
        while time.time() < deadline:
            hangar_ok = _check_count(client, base_url, "/api/v2/dronehunters/hangars", expected_hangar)
            hunter_ok = _check_count(client, base_url, "/api/v2/dronehunters", expected_hunters)
            print(f"    hangar (expect {expected_hangar}): {'OK' if hangar_ok else 'not yet'} | "
                  f"hunters (expect {expected_hunters}): {'OK' if hunter_ok else 'not yet'}")
            if hangar_ok and hunter_ok:
                print("    API counts match — settled.")
                settled = True
                break
            time.sleep(2)

        if not settled:
            print(f"    WARNING: API did not settle within {settle_wait}s.")

        auth.stop_auto_refresh()
        client.close()
    except Exception as e:
        print(f"    Could not check API: {e}")


def main():
    args = parse_args()

    print(f"=== Container Debug Script ===")
    print(f"Scenario    : {args.scenario}")
    print(f"Settle wait : {args.settle_wait}s")

    # Load config for optional API check
    cfg = {}
    if os.path.exists(args.config):
        with open(args.config) as f:
            cfg = json.load(f)

    use_api = not args.no_api and cfg.get("sd_url") and cfg.get("email") and cfg.get("password")
    if not use_api and not args.no_api:
        print("  (config.json not found or incomplete — skipping API settle check)")

    mgr = ContainerManager()
    if not mgr.client:
        print("ERROR: Docker is not available. Cannot run container debug.")
        sys.exit(1)

    print("\n--- Initial state ---")
    print_container_states(mgr.client)

    print("\n--- Saving initial state ---")
    mgr.save_initial_state()
    print("  Saved.")

    print(f"\n--- Applying scenario: {args.scenario} ---")
    mgr.apply_scenario(args.scenario)

    print("\n--- State after apply ---")
    print_container_states(mgr.client)

    if use_api:
        check_api_counts(
            cfg["sd_url"].rstrip("/"),
            cfg["email"],
            cfg["password"],
            args.scenario,
            args.settle_wait,
        )
    else:
        print(f"\n  Waiting {args.settle_wait}s for containers to stabilise...")
        time.sleep(args.settle_wait)

    print("\n--- State after settle wait ---")
    print_container_states(mgr.client)

    print("\n--- Restoring initial state ---")
    mgr.restore_initial_state()

    print("\n--- Final state (should match initial) ---")
    print_container_states(mgr.client)

    print("\nDone.")


if __name__ == "__main__":
    main()
