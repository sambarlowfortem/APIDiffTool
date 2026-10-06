#!/usr/bin/env python3
"""One-off script: parse SkyDome_Smart_API_5.2.3.html and print a skeleton endpoints.yaml.

Used to generate the initial version of endpoints.yaml. Not part of the prober pipeline.

Usage:
  python3 scripts/parse_docs.py /path/to/SkyDome_Smart_API_5.2.3.html
"""

import re
import sys

from bs4 import BeautifulSoup


def decode_section_id(section_id: str):
    """Decode a Redoc data-section-id into (tag, path, method) or (tag, None, None)."""
    # Format: tag/TagName  or  tag/TagName/paths/~1api~1v2~1.../method
    parts = section_id.split("/")
    if len(parts) < 2 or parts[0] != "tag":
        return None, None, None

    tag = parts[1]

    if len(parts) == 2:
        return tag, None, None  # section header

    if "paths" not in parts:
        return tag, None, None

    paths_idx = parts.index("paths")
    if paths_idx + 2 > len(parts) - 1:
        return tag, None, None

    raw_path = parts[paths_idx + 1]
    method = parts[paths_idx + 2].upper()

    # Decode ~1 → /
    path = raw_path.replace("~1", "/")

    return tag, path, method


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/parse_docs.py <html_file>")
        sys.exit(1)

    html_file = sys.argv[1]
    with open(html_file, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    sections = soup.find_all(attrs={"data-section-id": True})

    endpoints = {}
    current_tag = None

    for el in sections:
        sid = el.get("data-section-id", "")
        tag, path, method = decode_section_id(sid)
        if not tag:
            continue
        current_tag = tag
        if path and method:
            key = path
            if key not in endpoints:
                endpoints[key] = {"path": path, "methods": [], "tag": tag}
            if method not in endpoints[key]["methods"]:
                endpoints[key]["methods"].append(method)

    print("registry_version: 1")
    print()
    print("endpoints:")
    print()

    # Group by tag
    last_tag = None
    for path, ep in sorted(endpoints.items()):
        if ep["tag"] != last_tag:
            last_tag = ep["tag"]
            print(f"  # ─── {last_tag} {'─' * (60 - len(last_tag))}")
            print()

        methods_str = "[" + ", ".join(ep["methods"]) + "]"
        print(f"  - path: {path}")
        print(f"    methods: {methods_str}")

        # Extract path params
        params = re.findall(r'\{(\w+)\}', path)
        if params:
            print(f"    params:")
            for p in params:
                print(f"      {p}: {{ value: \"placeholder\" }}")

        print()


if __name__ == "__main__":
    main()
