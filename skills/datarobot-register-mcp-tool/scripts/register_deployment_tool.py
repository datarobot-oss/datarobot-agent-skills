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
from typing import Any

TOOL_NAME = "tool"
TOOL_VALUE = "tool"


def _has_tool_tag(tags: list[dict[str, Any]] | None) -> bool:
    return any(
        (t.get("name") == TOOL_NAME and t.get("value") == TOOL_VALUE)
        for t in (tags or [])
    )


def _already_tagged_error(exc: Exception) -> bool:
    """True if the error means the tool tag already exists (idempotent success)."""
    return (
        getattr(exc, "status_code", None) == 409 or "already in use" in str(exc).lower()
    )


def tag_as_tool(deployment: Any) -> list[dict[str, Any]]:
    """Idempotently tag a deployment `tool=tool` via the SDK's create_tag.

    The DataRobot SDK exposes deployment tags through dedicated methods
    (`create_tag(name, value)` / `delete_tag(id)` / `update_tag(...)`), not via
    `Deployment.update()`. Note that `Deployment.get(...).tags` is not always
    populated even when the deployment is tagged, so the pre-check can miss an
    existing tag; a 409 "already in use" from create_tag is therefore treated as
    idempotent success. Returns the deployment's tag list after the operation.
    """
    tags = list(deployment.tags or [])
    if _has_tool_tag(tags):
        return tags
    try:
        deployment.create_tag(TOOL_NAME, TOOL_VALUE)
    except Exception as exc:  # noqa: BLE001 - normalize SDK ClientError
        if _already_tagged_error(exc):
            return list(deployment.tags or []) or tags
        raise
    return list(deployment.tags or [])


def self_hosted_register_url(mcp_base_url: str, deployment_id: str) -> str:
    """Build the runtime registration URL for a self-hosted MCP server.

    The `registeredDeployments` route is a SIBLING of the `/mcp` protocol mount
    (both sit at the server root / directAccess base), not a child of it. So we
    strip a trailing `/mcp` segment before appending. Examples:
        http://host:8080/mcp/                         -> http://host:8080/registeredDeployments/<id>
        https://h/deployments/<d>/directAccess/mcp/   -> https://h/deployments/<d>/directAccess/registeredDeployments/<id>
    """
    base = mcp_base_url.rstrip("/")
    if base.endswith("/mcp"):
        base = base[: -len("/mcp")]
    return f"{base}/registeredDeployments/{deployment_id}"


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
