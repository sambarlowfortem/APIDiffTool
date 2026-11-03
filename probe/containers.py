"""Docker container management for probe scenarios."""

import json
import os
import time

import docker
import docker.errors


CONTAINER_NAMES = ["dronehangar", "dronehunter-1", "dronehunter-2", "dronehunter-3"]
DRONEHUNTER_NAMES = ["dronehunter-1", "dronehunter-2", "dronehunter-3"]

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
}

DEFAULT_IMAGES_CONFIG = "container_images.json"


def _extract_container_config(container) -> dict:
    """Extract the full runtime config from a container so it can be recreated with a different image.

    Captures environment variables (including takeoff-point coords), volumes, network mode,
    capabilities, and everything else needed to produce an equivalent container.
    """
    attrs = container.attrs
    config = attrs.get("Config", {})
    host_config = attrs.get("HostConfig", {})

    return {
        "image": config.get("Image", ""),
        "environment": config.get("Env") or [],
        "command": config.get("Cmd"),
        "entrypoint": config.get("Entrypoint"),
        "network_mode": host_config.get("NetworkMode", "bridge"),
        "binds": host_config.get("Binds") or [],
        "privileged": host_config.get("Privileged", False),
        "devices": host_config.get("Devices") or [],
        "extra_hosts": host_config.get("ExtraHosts") or [],
        "restart_policy": host_config.get("RestartPolicy") or {},
        "port_bindings": host_config.get("PortBindings") or {},
        "ipc_mode": host_config.get("IpcMode"),
        "cap_add": host_config.get("CapAdd") or [],
    }


class ContainerManager:
    def __init__(
        self,
        api_version: str = None,
        images_config_path: str = DEFAULT_IMAGES_CONFIG,
    ):
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"Warning: Docker not available ({e}). Container scenarios will be skipped.")
            self.client = None
        self._initial_states: dict[str, bool] = {}
        self._initial_configs: dict[str, dict] = {}
        self._reference_config: dict | None = None
        self._target_image: str | None = self._load_target_image(api_version, images_config_path)

    def _load_target_image(self, api_version: str | None, config_path: str) -> str | None:
        if not api_version:
            return None
        if not os.path.exists(config_path):
            print(f"Note: {config_path} not found — no version-specific container image will be applied")
            return None
        try:
            with open(config_path) as f:
                mapping = json.load(f)
        except Exception as e:
            print(f"Warning: could not read {config_path}: {e}")
            return None

        image = mapping.get(api_version)
        if image:
            print(f"Container image for v{api_version}: {image}")
        else:
            print(f"Note: no container image entry for v{api_version} in {config_path} — existing containers will be used as-is")
        return image

    def save_initial_state(self):
        """Record which containers are running and save their full configs (including image)."""
        if not self.client:
            return
        for name in CONTAINER_NAMES:
            try:
                c = self.client.containers.get(name)
                self._initial_states[name] = c.status == "running"
                self._initial_configs[name] = _extract_container_config(c)
            except docker.errors.NotFound:
                self._initial_states[name] = False
            except Exception as e:
                print(f"Warning: could not check container {name}: {e}")
                self._initial_states[name] = False

        # Use the first available dronehunter config as the reference template for
        # recreating containers with a different image.  This is what carries the
        # takeoff-point env vars into the new container.
        self._reference_config = None
        for name in DRONEHUNTER_NAMES:
            if name in self._initial_configs:
                self._reference_config = self._initial_configs[name]
                break

    def restore_initial_state(self):
        """Restore containers to their state at save_initial_state() time, reverting image if changed."""
        if not self.client:
            return
        for name, was_running in self._initial_states.items():
            try:
                c = self.client.containers.get(name)
                original_cfg = self._initial_configs.get(name) or {}
                original_image = original_cfg.get("image", "")
                current_image = c.attrs.get("Config", {}).get("Image", "")

                if original_image and current_image != original_image:
                    print(f"  Restoring: recreating {name} with original image {original_image}")
                    if c.status == "running":
                        c.stop()
                    c.remove()
                    c = self._create_container(name, original_image, original_cfg)

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
        """Start/stop containers to match the given scenario."""
        if not self.client:
            print(f"  [containers] Docker unavailable, skipping scenario setup")
            return

        desired = SCENARIOS.get(scenario_name)
        if desired is None:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        print(f"\n--- Container scenario: {scenario_name} ---")
        for name, should_run in desired.items():
            try:
                if should_run and name in DRONEHUNTER_NAMES and self._target_image:
                    self._ensure_dronehunter_image(name)

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
                    if name in DRONEHUNTER_NAMES and self._target_image and self._reference_config:
                        print(f"  {name} not found — creating with version image")
                        c = self._create_container(name, self._target_image, self._reference_config)
                        c.start()
                    else:
                        print(f"  Warning: container {name} not found, cannot start")
            except Exception as e:
                print(f"  Warning: error managing {name}: {e}")

    def _ensure_dronehunter_image(self, name: str):
        """Recreate the named dronehunter container if its image doesn't match the target.

        The replacement container gets its environment (including takeoff-point coords)
        and all other runtime config copied from the original.
        """
        try:
            c = self.client.containers.get(name)
        except docker.errors.NotFound:
            return  # caller handles the not-found case

        current_image = c.attrs.get("Config", {}).get("Image", "")
        if current_image == self._target_image:
            return

        print(f"  {name}: image mismatch")
        print(f"    current : {current_image}")
        print(f"    required: {self._target_image}")
        print(f"  Recreating {name} with required image...")

        # Prefer the saved initial config so we restore the original env/volumes exactly;
        # fall back to reading the live container if not saved yet.
        config = self._initial_configs.get(name) or _extract_container_config(c) or self._reference_config
        if not config:
            print(f"  Warning: no config available for {name}, skipping image switch")
            return

        if c.status == "running":
            c.stop()
        c.remove()
        self._create_container(name, self._target_image, config)

    def _create_container(self, name: str, image: str, config: dict):
        """Create (but do not start) a container with the given image and copied config."""
        kwargs: dict = {
            "image": image,
            "name": name,
            "detach": True,
            "environment": config.get("environment") or [],
            "network_mode": config.get("network_mode", "bridge"),
            "privileged": config.get("privileged", False),
        }
        if config.get("command"):
            kwargs["command"] = config["command"]
        if config.get("entrypoint"):
            kwargs["entrypoint"] = config["entrypoint"]
        if config.get("binds"):
            kwargs["volumes"] = config["binds"]
        if config.get("devices"):
            kwargs["devices"] = config["devices"]
        if config.get("extra_hosts"):
            kwargs["extra_hosts"] = config["extra_hosts"]
        if config.get("restart_policy"):
            kwargs["restart_policy"] = config["restart_policy"]
        if config.get("port_bindings"):
            kwargs["ports"] = config["port_bindings"]
        if config.get("ipc_mode"):
            kwargs["ipc_mode"] = config["ipc_mode"]
        if config.get("cap_add"):
            kwargs["cap_add"] = config["cap_add"]

        c = self.client.containers.create(**kwargs)
        print(f"  Created {name} with image {image}")
        return c

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
                print("  Service settled. Waiting 30s for background services to finish populating...")
                time.sleep(30)
                print("  Ready.")
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
