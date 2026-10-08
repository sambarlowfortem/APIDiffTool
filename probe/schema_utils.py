"""Utilities for inferring response schemas from JSON bodies."""

from .formats import detect, merge_formats

_TRACK_ID_PLACEHOLDER = "trackID"

# Array fields whose item structure is transient / timing-dependent.
# Recorded as arrays but not recursed into so their presence is stable across runs.
_OPAQUE_ARRAY_FIELDS = frozenset({"newPoints"})


def _is_dynamic_id_key(k: str) -> bool:
    """Return True if a dict key looks like a dynamic record ID rather than a field name.

    Track IDs (e.g. RED1567890) are alphanumeric and contain both letters and digits.
    Normal API field names (newPoints, trackFormat, type) contain only letters.
    """
    return k.isalnum() and any(c.isdigit() for c in k) and any(c.isalpha() for c in k)


def infer_schema_from_body(body, prefix: str = "") -> dict:
    """Flatten a JSON body into a dot-notation field→{type,format} dict."""
    result = {}
    _flatten(body, prefix, result)
    return result


def _flatten(value, prefix: str, result: dict):
    if isinstance(value, dict):
        # When all keys look like dynamic record IDs (e.g. track IDs), normalise them
        # to a single <trackID> placeholder so the schema is stable across runs.
        if value and all(_is_dynamic_id_key(k) for k in value):
            key = f"{prefix}.{_TRACK_ID_PLACEHOLDER}" if prefix else _TRACK_ID_PLACEHOLDER
            first_val = next(iter(value.values()))
            result[key] = {"type": "object"}
            _flatten(first_val, key, result)
            return
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                result[key] = {"type": "object"}
                _flatten(v, key, result)
            elif isinstance(v, list):
                result[key] = {"type": "array"}
                if v and k not in _OPAQUE_ARRAY_FIELDS:
                    item = v[0]
                    arr_key = f"{key}[]"
                    if isinstance(item, dict):
                        result[arr_key] = {"type": "object"}
                        _flatten(item, arr_key, result)
                    else:
                        fmt = detect(item)
                        result[arr_key] = {"type": _type_of(item), "format": fmt}
            else:
                fmt = detect(v)
                result[key] = {"type": _type_of(v), "format": fmt}
    elif isinstance(value, list):
        for i, item in enumerate(value[:1]):
            _flatten(item, prefix, result)


def _type_of(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "string"


def merge_schemas(base: dict, new: dict) -> dict:
    """Merge a new schema observation into the accumulated base schema.

    Fields present in both → merge format. Fields in new but not base → mark optional.
    """
    result = dict(base)
    for key, new_info in new.items():
        if key in result:
            existing = result[key]
            # Merge type (if differs, keep as string/text)
            merged_type = existing["type"] if existing["type"] == new_info["type"] else "string"
            # Merge format
            ef = existing.get("format")
            nf = new_info.get("format")
            if ef and nf:
                merged_format = merge_formats(ef, nf)
            else:
                merged_format = ef or nf
            result[key] = {"type": merged_type}
            if merged_format:
                result[key]["format"] = merged_format
            if "required" in existing:
                result[key]["required"] = existing["required"]
        else:
            result[key] = dict(new_info)
            result[key]["required"] = False  # only in some samples → optional
    return result


def finalize_schema(accumulated: dict, total_samples: int, present_counts: dict) -> dict:
    """Mark fields as required (present in all samples) or optional."""
    result = {}
    for key, info in sorted(accumulated.items()):
        entry = dict(info)
        count = present_counts.get(key, 0)
        entry["required"] = count >= total_samples
        result[key] = entry
    return result
