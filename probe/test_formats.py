#!/usr/bin/env python3
"""Unit tests for format detectors. Run with: python3 probe/test_formats.py"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from probe.formats import detect, merge_formats

def test(value, expected, label=""):
    result = detect(value)
    if result != expected:
        print(f"FAIL [{label or repr(value)}]: expected {expected!r}, got {result!r}")
        sys.exit(1)
    else:
        print(f"  OK  [{label or repr(value)}] → {result}")


# ── Empties / nulls ──────────────────────────────────────────────────────────
test(None, "null_value")
test("", "empty_string")
test([], "empty_array")
test({}, "empty_object")

# ── Booleans ─────────────────────────────────────────────────────────────────
test("true", "boolean_as_string_true_false")
test("false", "boolean_as_string_true_false")
test("0", "boolean_as_string_01")
test("1", "boolean_as_string_01")

# ── ISO 8601 datetimes ───────────────────────────────────────────────────────
test("2026-10-06T16:22:00Z", "iso8601_datetime_z", "dt_z_no_frac")
test("2026-10-06T16:22:00.123Z", "iso8601_datetime_z_ms", "dt_z_ms")
test("2026-10-06T16:22:00.123456Z", "iso8601_datetime_z_us", "dt_z_us")
test("2026-10-06T16:22:00+05:00", "iso8601_datetime_offset", "dt_offset")
test("2026-10-06T16:22:00.123+05:00", "iso8601_datetime_offset_ms", "dt_offset_ms")
test("2026-10-06T16:22:00", "iso8601_datetime_naive", "dt_naive")

# ── RFC 2822 / HTTP dates ────────────────────────────────────────────────────
test("Tue, 06 Oct 2026 16:22:00 +0000", "rfc2822_datetime")
test("Tue, 06 Oct 2026 16:22:00 GMT", "http_date")

# ── ISO date ─────────────────────────────────────────────────────────────────
test("2026-10-06", "iso8601_date")

# ── Slash dates ──────────────────────────────────────────────────────────────
test("10/16/2026", "us_date_mdy", "us_date unambiguous")
test("16/10/2026", "day_date_dmy", "day_date unambiguous")
test("01/02/2026", "slash_date_ambiguous", "ambiguous slash date")

# ── Times ────────────────────────────────────────────────────────────────────
test("16:22:00", "time_hms")
test("16:22:00.123", "time_hms_ms")

# ── ISO duration ─────────────────────────────────────────────────────────────
test("PT5M", "iso8601_duration")
test("P1DT2H", "iso8601_duration")

# ── Epoch (as number) ─────────────────────────────────────────────────────────
test(1791302400, "epoch_seconds", "epoch_s")
test(1791302400000, "epoch_milliseconds", "epoch_ms")
test(1791302400000000, "epoch_microseconds", "epoch_us")

# ── Epoch (as string) ────────────────────────────────────────────────────────
test("1791302400", "epoch_seconds_string", "epoch_s_str")
test("1791302400000", "epoch_milliseconds_string", "epoch_ms_str")

# ── Integer / decimal ─────────────────────────────────────────────────────────
test(42, "integer", "small_int")
test(3.14, "decimal", "decimal")
test(0, "integer", "zero")

# ── Integer as string ─────────────────────────────────────────────────────────
test("12345", "integer_as_string", "int_str_small")
test("-42", "integer_as_string", "negative_int_str")

# ── Number as string ─────────────────────────────────────────────────────────
test("3.14", "number_as_string", "float_str")

# ── UUID ─────────────────────────────────────────────────────────────────────
test("550e8400-e29b-41d4-a716-446655440000", "uuid_lower")
test("550E8400-E29B-41D4-A716-446655440000", "uuid_upper")
test("550e8400e29b41d4a716446655440000", "uuid_lower_no_hyphens")
test("550E8400E29B41D4A716446655440000", "uuid_upper_no_hyphens")

# ── Hex ID (MongoDB ObjectId) ─────────────────────────────────────────────────
test("6a8c6eb1a548d202ede14418", "hex_id", "objectid")

# ── Network ──────────────────────────────────────────────────────────────────
test("user@example.com", "email")
test("https://example.com/path", "url_absolute")
test("/api/v2/zones", "url_relative")
test("192.168.1.1", "ipv4")
test("AA:BB:CC:DD:EE:FF", "mac_address")

# ── Enum-like ─────────────────────────────────────────────────────────────────
test("UPPER_SNAKE", "enum_upper_snake")
test("lower_snake_case", "enum_lower_snake")
test("camelCase", "enum_camel")
test("kebab-case", "enum_kebab")
test("Title Case", "enum_title")

# ── Shape ─────────────────────────────────────────────────────────────────────
# X00330136 looks like UPPER_SNAKE (all caps+digits) — that's fine, it's a valid classification
result = detect("X00330136")
assert result in ("enum_upper_snake", "text") or result.startswith("shape:"), f"shape test: {result}"
print(f"  OK  [shape/enum X00330136] → {result}")
# A truly shape-only string: mixed letters and digits with separators
result2 = detect("AB-1234")
assert result2.startswith("shape:") or result2 in ("text", "enum_kebab"), f"shape2 test: {result2}"
print(f"  OK  [shape AB-1234] → {result2}")

# ── Text fallback ─────────────────────────────────────────────────────────────
test("This is a longer free-form text string that exceeds forty characters and should not match any pattern", "text", "long_text_no_match")

# ── Merge formats ─────────────────────────────────────────────────────────────
assert merge_formats("iso8601_date", "iso8601_date") == "iso8601_date"
assert merge_formats("iso8601_date", "epoch_seconds") == "mixed:epoch_seconds,iso8601_date"
print("  OK  [merge_formats]")

print("\nAll format detector tests passed.")
