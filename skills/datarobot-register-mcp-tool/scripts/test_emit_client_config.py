# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from emit_client_config import build_client_config


def test_hosted_url_uses_globalmcp_path():
    cfg = build_client_config(
        "https://app.datarobot.com", None, hosted=True, client="cursor"
    )
    url = cfg["mcpServers"]["datarobot"]["url"]
    assert url == "https://app.datarobot.com/api/v2/genai/globalmcp/mcp"


def test_self_hosted_url_uses_directaccess_path():
    cfg = build_client_config(
        "https://app.datarobot.com", "dep123", hosted=False, client="cursor"
    )
    url = cfg["mcpServers"]["datarobot"]["url"]
    assert url == "https://app.datarobot.com/deployments/dep123/directAccess/mcp/"


def test_self_hosted_requires_deployment_id():
    import pytest

    with pytest.raises(ValueError):
        build_client_config(
            "https://app.datarobot.com", None, hosted=False, client="cursor"
        )


def test_auth_header_present():
    cfg = build_client_config(
        "https://app.datarobot.com", None, hosted=True, client="cursor"
    )
    headers = cfg["mcpServers"]["datarobot"]["headers"]
    assert headers["Authorization"] == "Bearer ${DATAROBOT_API_TOKEN}"
