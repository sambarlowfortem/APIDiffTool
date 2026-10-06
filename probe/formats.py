"""Format detectors for response field values.

Ordered from most specific to most general. First match wins.
Bump FORMAT_DETECTORS_VERSION whenever this list changes.
"""

import re
import math

FORMAT_DETECTORS_VERSION = "1.0"

# ── helpers ──────────────────────────────────────────────────────────────────

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
_UUID_NOHYPHEN_RE = re.compile(r'^[0-9a-f]{32}$', re.I)
_HEX_ID_RE = re.compile(r'^[0-9a-f]{24}$')          # MongoDB ObjectId
_HEX_ID_UPPER_RE = re.compile(r'^[0-9A-F]{24}$')
_BASE64_RE = re.compile(r'^[A-Za-z0-9+/]+=*$')
_INT_STR_RE = re.compile(r'^-?\d+$')
_NUM_STR_RE = re.compile(r'^-?\d+(\.\d+)?([eE][+-]?\d+)?$')

_ISO_DT_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$')
_ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_TIME_RE = re.compile(r'^\d{2}:\d{2}:\d{2}(\.\d+)?$')
_ISO_DUR_RE = re.compile(r'^P(\d+Y)?(\d+M)?(\d+D)?(T(\d+H)?(\d+M)?(\d+S)?)?$')
_SLASH_DATE_RE = re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{4})$')
_RFC2822_RE = re.compile(
    r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} \w+ \d{4} \d{2}:\d{2}:\d{2} [+-]\d{4}$')
_HTTP_DATE_RE = re.compile(
    r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} \w+ \d{4} \d{2}:\d{2}:\d{2} GMT$')

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_URL_ABS_RE = re.compile(r'^https?://')
_URL_REL_RE = re.compile(r'^/')
_IPV4_RE = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
_IPV6_RE = re.compile(r'^[0-9a-fA-F:]+:[0-9a-fA-F:]*$')
_MAC_RE = re.compile(r'^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$')

_UPPER_SNAKE_RE = re.compile(r'^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$')
_LOWER_SNAKE_RE = re.compile(r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$')  # includes single words
_CAMEL_RE = re.compile(r'^[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*$')  # must have at least one uppercase
_KEBAB_RE = re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)+$')
_TITLE_RE = re.compile(r'^[A-Z][a-z]+( [A-Z][a-z]+)+$')

_SHAPE_CHAR_RE = re.compile(r'[a-zA-Z]')
_SHAPE_DIGIT_RE = re.compile(r'\d')

# Epoch plausible ranges (as floats for comparison)
_EPOCH_S_MIN = 1_000_000_000    # 2001-09-09
_EPOCH_S_MAX = 9_999_999_999    # 2286-11-20
_EPOCH_MS_MIN = 1_000_000_000_000
_EPOCH_MS_MAX = 9_999_999_999_999
_EPOCH_US_MIN = 1_000_000_000_000_000
_EPOCH_US_MAX = 9_999_999_999_999_999


def _detect_string(v: str):
    # Empties
    if v == "":
        return "empty_string"

    # Boolean-as-string
    if v in ("true", "false"):
        return "boolean_as_string_true_false"
    if v in ("0", "1") and len(v) == 1:
        return "boolean_as_string_01"

    # Datetime (most specific first)
    dt_m = _ISO_DT_RE.match(v)
    if dt_m:
        frac = dt_m.group(1)
        tz = dt_m.group(2)
        if tz == "Z":
            if frac is None:
                return "iso8601_datetime_z"
            digits = len(frac) - 1  # strip leading dot
            if digits <= 3:
                return "iso8601_datetime_z_ms"
            return "iso8601_datetime_z_us"
        elif tz and tz != "Z":
            if frac is None:
                return "iso8601_datetime_offset"
            return "iso8601_datetime_offset_ms"
        else:
            return "iso8601_datetime_naive"

    if _RFC2822_RE.match(v):
        return "rfc2822_datetime"
    if _HTTP_DATE_RE.match(v):
        return "http_date"

    # ISO date
    if _ISO_DATE_RE.match(v):
        return "iso8601_date"

    # Slash date
    sd = _SLASH_DATE_RE.match(v)
    if sd:
        a, b = int(sd.group(1)), int(sd.group(2))
        if a > 12:
            return "day_date_dmy"
        if b > 12:
            return "us_date_mdy"
        return "slash_date_ambiguous"

    # Time
    if _TIME_RE.match(v):
        tm = _TIME_RE.match(v)
        return "time_hms_ms" if tm.group(1) else "time_hms"

    # ISO duration
    if v.startswith("P") and _ISO_DUR_RE.match(v):
        return "iso8601_duration"

    # Epoch as string
    if _INT_STR_RE.match(v):
        n = int(v)
        if _EPOCH_S_MIN <= n <= _EPOCH_S_MAX:
            return "epoch_seconds_string"
        if _EPOCH_MS_MIN <= n <= _EPOCH_MS_MAX:
            return "epoch_milliseconds_string"
        return "integer_as_string"

    if _NUM_STR_RE.match(v):
        return "number_as_string"

    # Network
    if _EMAIL_RE.match(v):
        return "email"
    if _URL_ABS_RE.match(v):
        return "url_absolute"
    if _URL_REL_RE.match(v):
        return "url_relative"
    if _IPV4_RE.match(v):
        parts = v.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return "ipv4"
    if _MAC_RE.match(v):
        return "mac_address"
    if _IPV6_RE.match(v) and v.count(":") >= 2:
        return "ipv6"

    # UUID
    if _UUID_RE.match(v):
        if v == v.lower():
            return "uuid_lower"
        if v == v.upper():
            return "uuid_upper"
        return "uuid_lower"  # mixed case → treat as lower

    # UUID without hyphens
    if _UUID_NOHYPHEN_RE.match(v):
        if v == v.lower():
            return "uuid_lower_no_hyphens"
        if v == v.upper():
            return "uuid_upper_no_hyphens"
        return "uuid_lower_no_hyphens"

    # Hex ID (MongoDB ObjectId — exactly 24 hex chars)
    if _HEX_ID_RE.match(v):
        return "hex_id"
    if _HEX_ID_UPPER_RE.match(v):
        return "hex_id"

    # Base64 (at least 4 chars, length multiple of 4, not already matched)
    if len(v) >= 4 and len(v) % 4 == 0 and _BASE64_RE.match(v):
        return "base64"

    # Enum-like (short, no spaces unless title)
    if " " not in v:
        if _UPPER_SNAKE_RE.match(v):
            return "enum_upper_snake"
        if _LOWER_SNAKE_RE.match(v):
            return "enum_lower_snake"
        if _CAMEL_RE.match(v):
            return "enum_camel"
        if _KEBAB_RE.match(v):
            return "enum_kebab"
    else:
        if _TITLE_RE.match(v):
            return "enum_title"

    # Short unknown string → shape
    if len(v) <= 40:
        shape = _to_shape(v)
        if shape and _is_consistent_shape(shape, v):
            return f"shape:{shape}"

    return "text"


def _to_shape(v: str) -> str:
    result = []
    for ch in v:
        if ch.isalpha():
            result.append("A")
        elif ch.isdigit():
            result.append("9")
        else:
            result.append(ch)
    return "".join(result)


def _is_consistent_shape(shape: str, v: str) -> bool:
    return bool(re.search(r'[A9]', shape))


def detect(value) -> str:
    """Return the format name for a single value."""
    if value is None:
        return "null_value"
    if isinstance(value, bool):
        return "boolean_as_string_true_false"  # booleans in JSON stay as bool type
    if isinstance(value, int):
        n = value
        if _EPOCH_S_MIN <= n <= _EPOCH_S_MAX:
            return "epoch_seconds"
        if _EPOCH_MS_MIN <= n <= _EPOCH_MS_MAX:
            return "epoch_milliseconds"
        if _EPOCH_US_MIN <= n <= _EPOCH_US_MAX:
            return "epoch_microseconds"
        return "integer"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "decimal"
        if value == int(value) and _EPOCH_S_MIN <= int(value) <= _EPOCH_S_MAX:
            return "epoch_seconds"
        return "decimal"
    if isinstance(value, list):
        if len(value) == 0:
            return "empty_array"
        return None  # arrays are handled at schema inference level
    if isinstance(value, dict):
        if len(value) == 0:
            return "empty_object"
        return None  # objects handled recursively
    if isinstance(value, str):
        return _detect_string(value)
    return "text"


def merge_formats(f1: str, f2: str) -> str:
    """Merge two format names from different samples of the same field."""
    if f1 == f2:
        return f1
    # Combine as mixed
    parts1 = set(f1.split(",")) if f1.startswith("mixed:") else {f1}
    parts2 = set(f2.split(",")) if f2.startswith("mixed:") else {f2}
    combined = sorted(parts1 | parts2)
    return "mixed:" + ",".join(combined)
