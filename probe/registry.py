"""Registry loader and validator for endpoints.yaml."""

import hashlib
import os
import re

import jsonschema
import yaml


class RegistryError(Exception):
    pass


def load_registry(yaml_path: str, schema_path: str) -> dict:
    """Load, validate, and return the parsed registry dict.

    Raises RegistryError with a clear message on any failure.
    """
    if not os.path.exists(yaml_path):
        raise RegistryError(f"Registry file not found: {yaml_path}")
    if not os.path.exists(schema_path):
        raise RegistryError(f"Registry schema not found: {schema_path}")

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw_bytes = f.read()
        registry = yaml.safe_load(raw_bytes)
    except yaml.YAMLError as e:
        raise RegistryError(f"YAML parse error in {yaml_path}: {e}")

    import json
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        raise RegistryError(f"Could not load registry schema {schema_path}: {e}")

    try:
        jsonschema.validate(instance=registry, schema=schema)
    except jsonschema.ValidationError as e:
        path = " -> ".join(str(p) for p in e.absolute_path) or "(root)"
        raise RegistryError(
            f"Registry validation failed at {path}:\n  {e.message}\n\n"
            f"Fix {yaml_path} and re-run."
        )

    registry["_sha256"] = hashlib.sha256(raw_bytes.encode("utf-8")).hexdigest()
    registry["_yaml_path"] = yaml_path
    return registry


def resolve_deprecated(endpoint: dict, method: str) -> dict | None:
    """Return the deprecation info for an endpoint+method, or None."""
    deprecated = endpoint.get("deprecated")
    if not deprecated:
        return None
    if method in deprecated:
        return deprecated[method]
    if "*" in deprecated:
        return deprecated["*"]
    return None


def get_listed_methods(endpoint: dict) -> list[str]:
    return list(endpoint.get("methods", []))


def get_all_methods() -> list[str]:
    return ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def extract_path_params(path: str) -> list[str]:
    return re.findall(r'\{(\w+)\}', path)


class ParamResolver:
    """Resolves path parameters by calling dependency endpoints."""

    def __init__(self, registry: dict, http_fn):
        """
        http_fn: callable(method, url, **kwargs) → response with .status_code, .json()
        """
        self._registry = registry
        self._http = http_fn
        self._cache: dict[str, dict] = {}  # "METHOD /path" → response json

    def resolve(self, endpoint: dict, base_url: str) -> dict[str, str] | None:
        """
        Return a dict of {param_name: resolved_value} for all params in endpoint.
        Returns None if any param cannot be resolved.
        """
        params_spec = endpoint.get("params", {})
        path = endpoint["path"]
        needed = extract_path_params(path)

        resolved = {}
        for param in needed:
            spec = params_spec.get(param)
            if spec is None:
                return None  # unresolvable

            if "value" in spec:
                resolved[param] = spec["value"]
            elif "from" in spec:
                key = spec["from"]   # e.g. "POST /api/v2/zones"
                field = spec["field"]
                value = self._resolve_from(key, field, base_url)
                if value is None:
                    return None
                resolved[param] = str(value)
            else:
                return None

        return resolved

    def _resolve_from(self, key: str, field: str, base_url: str):
        """Call the dependency endpoint and extract the field."""
        if key in self._cache:
            data = self._cache[key]
        else:
            parts = key.split(" ", 1)
            if len(parts) != 2:
                return None
            method, path = parts
            # Find the endpoint in the registry to get its body
            body = self._find_body(method, path)
            url = base_url.rstrip("/") + path
            try:
                if body and method in ("POST", "PUT", "PATCH"):
                    resp = self._http(method, url, json=body)
                else:
                    resp = self._http(method, url)
                if resp.status_code >= 300:
                    return None
                data = resp.json()
            except Exception:
                return None
            self._cache[key] = data

        return _extract_field(data, field)

    def _find_body(self, method: str, path: str) -> dict | None:
        for ep in self._registry.get("endpoints", []):
            if ep["path"] == path:
                return (ep.get("body") or {}).get(method)
        return None


def _extract_field(data, field: str):
    """Extract a top-level or nested field from a JSON response."""
    if isinstance(data, dict):
        if field in data:
            return data[field]
        # Try common wrappers
        for wrapper in ("data", "result"):
            inner = data.get(wrapper)
            if isinstance(inner, dict) and field in inner:
                return inner[field]
            if isinstance(inner, list) and inner:
                if isinstance(inner[0], dict) and field in inner[0]:
                    return inner[0][field]
    if isinstance(data, list) and data:
        return _extract_field(data[0], field)
    return None
