#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify a tagged deployment shows up as an MCP tool.

Usage:
    python verify_mcp_tool.py <deployment_id> --mcp-url <url>
"""
import argparse
import os
import sys


def tool_name_for_deployment(deployment_id: str, tools: list[dict]) -> str | None:
    for tool in tools:
        meta = tool.get("meta") or {}
        if meta.get("deployment_id") == deployment_id:
            return tool.get("name")
    return None


def assert_tool_present(deployment_id: str, tools: list[dict]) -> bool:
    return tool_name_for_deployment(deployment_id, tools) is not None


def list_tools(mcp_url: str, token: str) -> list[dict]:
    """Connect to the MCP server and return the tools/list payload as dicts.

    IMPLEMENTER: build with the streamable-HTTP MCP client and confirm the
    tool name/meta shape against a live deployment (see Task B6). The metadata
    key that carries the deployment id MUST be verified, not assumed.
    """
    raise NotImplementedError("wire up the MCP streamable-HTTP client; verify in B6")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("deployment_id")
    p.add_argument("--mcp-url", required=True)
    args = p.parse_args(argv[1:])
    tools = list_tools(args.mcp_url, os.getenv("DATAROBOT_API_TOKEN"))
    name = tool_name_for_deployment(args.deployment_id, tools)
    if name:
        print(f"OK: deployment {args.deployment_id} is exposed as tool '{name}'.")
        return 0
    print(f"NOT FOUND: deployment {args.deployment_id} is not in tools/list. "
          "Hosted: reconnect client + check the feature flag. Self-hosted: register/restart.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
