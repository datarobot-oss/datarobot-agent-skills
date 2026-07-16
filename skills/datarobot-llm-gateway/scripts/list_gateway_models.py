#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""List active LLM Gateway models as JSON.

Reads DataRobot endpoint and API token from `$XDG_CONFIG_HOME/datarobot/drconfig.yaml`
(default `~/.config/datarobot/drconfig.yaml`), the file populated by `dr auth login`.
The token is used to authenticate the request and is never emitted in the output.

Usage: python list_gateway_models.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def _load_drconfig() -> tuple[str | None, str | None]:
    """Return (endpoint, token) from drconfig.yaml, or (None, None) if unavailable."""
    root = os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = Path(root) / "datarobot" / "drconfig.yaml"
    if not path.exists():
        return None, None
    endpoint, token = None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(endpoint|token)\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip("'\"")
        if key == "endpoint":
            endpoint = value
        else:
            token = value
    return endpoint, token


def main() -> int:
    endpoint, token = _load_drconfig()
    if not endpoint or not token:
        print(
            "Error: DataRobot credentials not found in "
            "$XDG_CONFIG_HOME/datarobot/drconfig.yaml. "
            "Run `dr auth login` to authenticate.",
            file=sys.stderr,
        )
        return 1

    url = f"{endpoint.rstrip('/')}/genai/llmgw/catalog/"
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - trusted endpoint
            payload = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        print(f"Error fetching catalog: {exc.reason}", file=sys.stderr)
        return 1

    raw = payload["data"] if isinstance(payload, dict) else payload
    models = []
    for m in raw:
        if not m.get("isActive"):
            continue
        name = m.get("model", "")
        if name and not name.startswith("datarobot/"):
            name = f"datarobot/{name}"
        models.append(
            {
                "name": name,
                "provider": m.get("provider", ""),
                "context_size": m.get("contextSize", 0),
            }
        )
    models.sort(key=lambda m: (m["provider"], m["name"]))
    print(json.dumps(models, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
