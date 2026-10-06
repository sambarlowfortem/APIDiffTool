"""Docker container management for probe scenarios."""

import time

import docker
import docker.errors


CONTAINER_NAMES = ["dronehangar", "dronehunter-1", "dronehunter-2", "dronehunter-3"]

SCENARIOS = {
    "no_containers": {
        "dronehangar": False,
        "dronehunter-1": False,
        "dronehunter-2": False,
        "dronehunter-3": False,
    },
    "containers_present": {
        "dronehangar": True,
        "dronehunter-1": True,
        "dronehunter-2": False,
        "dronehunter-3": False,
    },
    "multiple_hunters": {
        "dronehangar": True,
        "dronehunter-1": True,
        "dronehunter-2": True,
        "dronehunter-3": True,
    },
}


class ContainerManager:
    def __init__(self):
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"Warning: Docker not available ({e}). Container scenarios will be skipped.")
            self.client = None
        self._initial_states: dict[str, bool] = {}

    def save_initial_state(self):
        """Record which containers are currently running."""
        if not self.client:
            return
        for name in CONTAINER_NAMES:
            try:
                c = self.client.containers.get(name)
                self._initial_states[name] = c.status == "running"
            except docker.errors.NotFound:
                self._initial_states[name] = False
            except Exception as e:
                print(f"Warning: could not check container {name}: {e}")
                self._initial_states[name] = False

    def restore_initial_state(self):
        """Restore containers to their state at save_initial_state() time."""
        if not self.client:
            return
        for name, was_running in self._initial_states.items():
            try:
                c = self.client.containers.get(name)
                currently_running = c.status == "running"
                if was_running and not currently_running:
                    print(f"  Restoring: starting {name}")
                    c.start()
                elif not was_running and currently_running:
                    print(f"  Restoring: stopping {name}")
                    c.stop()
            except docker.errors.NotFound:
                pass
            except Exception as e:
                print(f"Warning: could not restore {name}: {e}")

    def apply_scenario(self, scenario_name: str, settle_wait: int = 20):
        """Start/stop containers to match the given scenario, then wait for settle."""
        if not self.client:
            print(f"  [containers] Docker unavailable, skipping scenario setup")
            return

        desired = SCENARIOS.get(scenario_name)
        if desired is None:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        print(f"\n--- Container scenario: {scenario_name} ---")
        for name, should_run in desired.items():
            try:
                c = self.client.containers.get(name)
                is_running = c.status == "running"
                if should_run and not is_running:
                    print(f"  Starting {name}")
                    c.start()
                elif not should_run and is_running:
                    print(f"  Stopping {name}")
                    c.stop()
                else:
                    state = "running" if is_running else "stopped"
                    print(f"  {name}: already {state}")
            except docker.errors.NotFound:
                if should_run:
                    print(f"  Warning: container {name} not found, cannot start")
            except Exception as e:
                print(f"  Warning: error managing {name}: {e}")

    def wait_for_settle(
        self,
        expected_hangar: int,
        expected_hunters: int,
        api_client,
        base_url: str,
        settle_wait: int = 20,
    ):
        """Poll the API until it reflects the expected container counts."""
        deadline = time.time() + settle_wait
        while time.time() < deadline:
            hangar_ok = _check_count(api_client, base_url, "/api/v2/dronehunters/hangars", expected_hangar)
            hunter_ok = _check_count(api_client, base_url, "/api/v2/dronehunters", expected_hunters)
            if hangar_ok and hunter_ok:
                print("  Service settled.")
                return
            time.sleep(2)
        print(f"  Warning: service did not settle within {settle_wait}s, continuing anyway.")


def _check_count(client, base_url: str, path: str, expected: int) -> bool:
    url = base_url.rstrip("/") + path
    try:
        r = client.request("GET", url)
        if r.status_code == 200:
            data = r.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(items, list):
                return len(items) == expected
            return expected == 0
    except Exception:
        pass
    return expected == 0
