#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify a tagged deployment shows up as an MCP tool.

The MCP server names a deployment-tool after the SLUGIFIED deployment label
(datarobot-genai's `_convert_tool_string`), not the deployment id. `meta` only
carries `{"tool_category": "USER_TOOL_DEPLOYMENT"}`; the id may appear on
`annotations.deployment_id` but is not guaranteed on the wire. We match by
slugified label, scoped to that tool_category, with title/annotation corroboration.

Usage:
    python verify_mcp_tool.py <deployment_id> --mcp-url <url>
"""

import argparse
import os
import re
import sys

DEPLOYMENT_TOOL_CATEGORY = "USER_TOOL_DEPLOYMENT"


def _as_dict(obj) -> dict:
    """Normalize meta/annotations to a plain dict (fastmcp may return a model)."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:  # noqa: BLE001
            pass
    try:
        return dict(obj)
    except Exception:  # noqa: BLE001
        return {}


def slugify_tool_name(label: str) -> str:
    s = re.sub(r"\[.*?\]", "", label or "")
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_]", "", s)
    s = s.lower()
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def expected_tool_name(
    label: str | None, deployment_id: str, metadata_name: str | None = None
) -> str:
    base = label or metadata_name or f"deployment_{deployment_id}"
    return slugify_tool_name(base) or f"deployment_{deployment_id}"


def find_deployment_tool(
    tools: list[dict],
    label: str | None,
    deployment_id: str,
    metadata_name: str | None = None,
) -> dict | None:
    want = expected_tool_name(label, deployment_id, metadata_name)
    dep_tools = [
        t
        for t in tools
        if _as_dict(t.get("meta")).get("tool_category") == DEPLOYMENT_TOOL_CATEGORY
    ]
    # Authoritative match: the slugified name, or an explicit annotations.deployment_id.
    for tool in dep_tools:
        ann = _as_dict(tool.get("annotations"))
        if tool.get("name") == want or (
            deployment_id and ann.get("deployment_id") == deployment_id
        ):
            return tool
    # Fallback corroboration: exact title == label. Labels are not guaranteed unique,
    # so this only runs when no authoritative match was found.
    if label:
        for tool in dep_tools:
            if tool.get("title") == label:
                return tool
    return None


def assert_tool_present(
    tools: list[dict],
    label: str | None,
    deployment_id: str,
    metadata_name: str | None = None,
) -> bool:
    return find_deployment_tool(tools, label, deployment_id, metadata_name) is not None


def list_tools(mcp_url: str, token: str) -> list[dict]:
    """Connect to the MCP server (streamable-HTTP) and return tools as dicts.

    Uses fastmcp's high-level client. NOTE: confirm the installed fastmcp's
    Client/transport API; this targets fastmcp>=2. Only invoked by the live
    e2e test (skipped unless creds are set), so it is not unit-tested here.
    """
    import asyncio

    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    async def _run() -> list[dict]:
        transport = StreamableHttpTransport(
            mcp_url, headers={"Authorization": f"Bearer {token}"}
        )
        async with Client(transport) as client:
            out = []
            for t in await client.list_tools():
                out.append(
                    {
                        "name": t.name,
                        "title": getattr(t, "title", None),
                        "meta": _as_dict(getattr(t, "meta", None)),
                        "annotations": _as_dict(getattr(t, "annotations", None)),
                    }
                )
            return out

    return asyncio.run(_run())


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("deployment_id")
    p.add_argument("--mcp-url", required=True)
    args = p.parse_args(argv[1:])

    dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )
    deployment = dr.Deployment.get(args.deployment_id)
    label = getattr(deployment, "label", None)
    tools = list_tools(args.mcp_url, os.getenv("DATAROBOT_API_TOKEN"))
    tool = find_deployment_tool(tools, label, args.deployment_id)
    if tool:
        print(
            f"OK: deployment {args.deployment_id} is exposed as tool '{tool['name']}'."
        )
        return 0
    print(
        f"NOT FOUND: deployment {args.deployment_id} is not in tools/list. "
        "Hosted: reconnect client + check the feature flag. Self-hosted: register/restart."
    )
    # Print what tools/list actually returned, to help diagnose the mismatch.
    print(f"tools/list returned {len(tools)} tool(s):", file=sys.stderr)
    for t in tools:
        cat = _as_dict(t.get("meta")).get("tool_category")
        print(
            f"  - {t.get('name')} (title={t.get('title')!r}, category={cat})",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
