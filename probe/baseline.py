"""Record the not-found signature for this API instance."""

import random
import string

from .formats import detect
from .schema_utils import infer_schema_from_body


def _random_suffix(n=8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _sig_from_response(resp) -> dict:
    status = resp.status_code
    ct = resp.headers.get("content-type", "")
    body_schema = {}
    try:
        body = resp.json()
        body_schema = infer_schema_from_body(body)
    except Exception:
        pass
    return {"status": status, "content_type": ct, "body_schema": body_schema}


def _sigs_equal(a: dict, b: dict) -> bool:
    return a["status"] == b["status"] and a["content_type"] == b["content_type"]


def record_not_found_baseline(client, base_url: str, _format_detector=None) -> dict:
    """Send GET+POST to three random non-existent routes and record the signature.

    Returns a single not_found_signature dict if all six responses agree,
    or a dict keyed by pattern name if they differ.
    """
    base = base_url.rstrip("/")
    patterns = {
        "root": f"/__probe_missing_{_random_suffix()}",
        "api_v2": f"/api/v2/__probe_missing_{_random_suffix()}",
        "nested": f"/api/v2/some/__probe_missing_{_random_suffix()}",
    }

    all_sigs = {}
    for name, path in patterns.items():
        url = base + path
        for method in ("GET", "POST"):
            key = f"{name}_{method.lower()}"
            try:
                r = client.request(method, url)
                all_sigs[key] = _sig_from_response(r)
            except Exception:
                pass

    if not all_sigs:
        return {"status": 404, "content_type": "", "body_schema": {}}

    # Check if all agree
    sigs_list = list(all_sigs.values())
    first = sigs_list[0]
    if all(_sigs_equal(s, first) for s in sigs_list[1:]):
        # Merge body schemas
        return first

    # They differ — return by pattern
    return {
        name: all_sigs.get(f"{name}_get", all_sigs.get(f"{name}_post", {}))
        for name in patterns
    }


def matches_not_found(response, signature: dict) -> bool:
    """Return True if this response matches the not-found signature."""
    if isinstance(signature, dict) and "status" in signature:
        return (
            response.status_code == signature["status"]
            and response.headers.get("content-type", "").split(";")[0].strip()
            == signature.get("content_type", "").split(";")[0].strip()
        )
    # Multiple signatures — match any
    if isinstance(signature, dict):
        for sig in signature.values():
            if isinstance(sig, dict) and "status" in sig:
                if (
                    response.status_code == sig["status"]
                    and response.headers.get("content-type", "").split(";")[0].strip()
                    == sig.get("content_type", "").split(";")[0].strip()
                ):
                    return True
    return False
