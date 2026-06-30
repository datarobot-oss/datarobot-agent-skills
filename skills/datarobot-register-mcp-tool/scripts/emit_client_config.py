#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Emit MCP client config for connecting to a DataRobot MCP server.

Usage:
    python emit_client_config.py --host https://app.datarobot.com --hosted
    python emit_client_config.py --host https://app.datarobot.com --deployment-id dep123 --self-hosted
"""

import argparse
import json
import sys


def build_client_config(
    host: str, deployment_id: str | None, hosted: bool, client: str
) -> dict:
    # client param (claude/cursor) is accepted for forward-compatibility; currently emitted config is identical
    host = host.rstrip("/")
    if hosted:
        url = f"{host}/api/v2/genai/globalmcp/mcp"
    else:
        if not deployment_id:
            raise ValueError("self-hosted config requires a deployment_id")
        url = f"{host}/deployments/{deployment_id}/directAccess/mcp/"
    return {
        "mcpServers": {
            "datarobot": {
                "url": url,
                "headers": {"Authorization": "Bearer ${DATAROBOT_API_TOKEN}"},
            }
        }
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--deployment-id")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hosted", action="store_true")
    mode.add_argument("--self-hosted", dest="self_hosted", action="store_true")
    p.add_argument("--client", choices=["claude", "cursor"], default="cursor")
    args = p.parse_args(argv[1:])
    cfg = build_client_config(args.host, args.deployment_id, args.hosted, args.client)
    print(json.dumps(cfg, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
