#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Check the hosted Global MCP tool-gallery feature flag.

The flag (`ENABLE_MCP_TOOLS_GALLERY_SUPPORT`) is read-only via the public API.
There is no public write — if disabled, an on-prem admin toggles it, or a cloud
customer requests it from DataRobot (ref PBMP-7644). Self-hosted MCP ignores it.

Usage:
    python check_tool_gallery_flag.py
"""

import os
import sys
from typing import Any

FLAG = "ENABLE_MCP_TOOLS_GALLERY_SUPPORT"


def is_tool_gallery_enabled(client: Any) -> bool:
    resp = client.post(
        "entitlements/evaluate/",
        data={"entitlements": [{"name": FLAG}]},
    )
    payload = resp.json()
    for ent in payload.get("entitlements", []):
        if ent.get("name") == FLAG:
            value = ent.get("value")
            if isinstance(value, str):
                return value.strip().lower() == "true"
            return bool(value)
    return False


def main(argv: list[str]) -> int:
    import datarobot as dr

    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )
    enabled = is_tool_gallery_enabled(client)
    if enabled:
        print(f"{FLAG}: ENABLED — tagged deployments will appear on the hosted MCP.")
        return 0
    print(
        f"{FLAG}: DISABLED.\n"
        "  - On-prem: an org admin can enable it in the admin console.\n"
        "  - Cloud: request enablement from DataRobot (ref PBMP-7644).\n"
        "  - Unblocked alternative: self-host the MCP server (it ignores this flag)."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
