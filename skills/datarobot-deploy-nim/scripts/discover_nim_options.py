#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Discover NIM templates and GPU resource bundles.

Lists NIM container templates (GET /customTemplates/?templateSubType=NIM_CONTAINERS)
and GPU resource bundles (ResourceBundle.list(use_cases=["customModel"])).

Usage:
    python discover_nim_options.py [--name <template name substring>]
"""
import argparse
import os
import sys


def filter_gpu_bundles(bundles: list) -> list:
    gpu = [b for b in bundles if getattr(b, "has_gpu", False)]
    return sorted(gpu, key=lambda b: (getattr(b, "gpu_count", 0), getattr(b, "gpu_memory_bytes", 0)))


def pick_nim_template(templates: list[dict], name_substr: str | None = None) -> dict | None:
    if not templates:
        return None
    if name_substr is None:
        return templates[0]
    needle = name_substr.lower()
    for t in templates:
        if needle in (t.get("name") or "").lower():
            return t
    return None


def main(argv: list[str]) -> int:
    import datarobot as dr
    from datarobot.models.resource_bundle import ResourceBundle

    p = argparse.ArgumentParser()
    p.add_argument("--name", help="filter NIM template by name substring")
    args = p.parse_args(argv[1:])

    client = dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
                       endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))
    resp = client.get("customTemplates/", params={"templateSubType": "NIM_CONTAINERS"})
    templates = resp.json().get("data", [])
    chosen = pick_nim_template(templates, args.name)
    print("NIM templates:")
    for t in templates:
        marker = " <- chosen" if chosen and t.get("id") == chosen.get("id") else ""
        print(f"  {t.get('id')}\t{t.get('name')}{marker}")

    if chosen:
        print(f"Chosen template id: {chosen.get('id')} (pass to create_nim_from_template.py --template-id)")

    print("GPU resource bundles (use with --resource-bundle-id):")
    for b in filter_gpu_bundles(ResourceBundle.list(use_cases=["customModel"])):
        print(f"  {b.id}\t{b.name}\tgpu_count={b.gpu_count}\tgpu_mem={b.gpu_memory_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
