#!/usr/bin/env python3
# Copyright 2026 DataRobot, Inc.
# SPDX-License-Identifier: Apache-2.0
"""List active LLM Gateway models as JSON.

Reads DATAROBOT_ENDPOINT / DATAROBOT_API_TOKEN from .env (if present) or the
environment. The token is used to authenticate the request and is never emitted
in the output.

Usage: python list_gateway_models.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def _from_env_file(key: str) -> str | None:
    path = Path(".env")
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            return value
    return None


def main() -> int:
    endpoint = _from_env_file("DATAROBOT_ENDPOINT") or os.getenv("DATAROBOT_ENDPOINT")
    token = _from_env_file("DATAROBOT_API_TOKEN") or os.getenv("DATAROBOT_API_TOKEN")
    if not endpoint or not token:
        print(
            "Error: DATAROBOT_ENDPOINT or DATAROBOT_API_TOKEN not set. "
            "Run `dr dotenv update`.",
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
        models.append({
            "name": name,
            "provider": m.get("provider", ""),
            "context_size": m.get("contextSize", 0),
        })
    models.sort(key=lambda m: (m["provider"], m["name"]))
    print(json.dumps(models, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
