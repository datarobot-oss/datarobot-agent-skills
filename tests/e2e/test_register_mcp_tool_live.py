# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Live e2e: tag a real deployment and confirm it surfaces as an MCP tool."""

import os
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "skills/datarobot-register-mcp-tool/scripts"
)
sys.path.insert(0, str(SCRIPTS))

REQUIRED = ["DATAROBOT_ENDPOINT", "DATAROBOT_API_TOKEN", "E2E_TEST_DEPLOYMENT_ID"]
pytestmark = pytest.mark.skipif(
    any(not os.getenv(v) for v in REQUIRED),
    reason=f"set {REQUIRED} to run the live MCP registration test",
)


def test_tag_and_surface_real_deployment():
    import datarobot as dr
    from register_deployment_tool import tag_as_tool
    from verify_mcp_tool import list_tools, assert_tool_present

    dep_id = os.environ["E2E_TEST_DEPLOYMENT_ID"]
    dr.Client(
        token=os.environ["DATAROBOT_API_TOKEN"],
        endpoint=os.environ["DATAROBOT_ENDPOINT"],
    )
    deployment = dr.Deployment.get(dep_id)
    tag_as_tool(deployment)

    endpoint = os.environ["DATAROBOT_ENDPOINT"].rstrip("/")
    if not endpoint.endswith("/api/v2"):
        endpoint += "/api/v2"
    mcp_url = endpoint + "/genai/globalmcp/mcp"
    tools = list_tools(mcp_url, os.environ["DATAROBOT_API_TOKEN"])
    assert assert_tool_present(tools, getattr(deployment, "label", None), dep_id), (
        "deployment tagged but not present in tools/list — "
        "check ENABLE_MCP_TOOLS_GALLERY_SUPPORT and client/list caching"
    )
