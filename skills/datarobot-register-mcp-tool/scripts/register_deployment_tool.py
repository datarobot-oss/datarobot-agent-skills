#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tag a deployment as an MCP tool, and (self-hosted) register it at runtime.

Hosted Global MCP: tagging is enough; the client must reconnect to see the tool.
Self-hosted MCP: tag, then PUT /registeredDeployments/{id} (no restart) OR restart
with MCP_SERVER_REGISTER_DYNAMIC_TOOLS_ON_STARTUP=true.

Usage:
    python register_deployment_tool.py <deployment_id>
    python register_deployment_tool.py <deployment_id> --self-hosted-mcp-url <url>
"""
import argparse
import os
import sys

TOOL_TAG = {"name": "tool", "value": "tool"}


def tag_as_tool(deployment) -> list[dict]:
    tags = list(deployment.tags or [])
    if TOOL_TAG in tags:
        return tags
    tags.append(TOOL_TAG)
    deployment.update(tags=tags)
    return tags


def self_hosted_register_url(mcp_base_url: str, deployment_id: str) -> str:
    base = mcp_base_url if mcp_base_url.endswith("/") else mcp_base_url + "/"
    return f"{base}registeredDeployments/{deployment_id}"


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("deployment_id")
    p.add_argument("--self-hosted-mcp-url", dest="self_hosted_mcp_url")
    args = p.parse_args(argv[1:])

    dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )
    deployment = dr.Deployment.get(args.deployment_id)
    tag_as_tool(deployment)
    print(f"Tagged deployment {args.deployment_id} with tool=tool.")

    if args.self_hosted_mcp_url:
        import requests

        url = self_hosted_register_url(args.self_hosted_mcp_url, args.deployment_id)
        resp = requests.put(
            url,
            headers={"Authorization": f"Bearer {os.getenv('DATAROBOT_API_TOKEN')}"},
            timeout=30,
        )
        resp.raise_for_status()
        print(f"Registered with self-hosted MCP at {url} (status {resp.status_code}).")
    else:
        print("Hosted MCP: reconnect your client to pick up the new tool.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
