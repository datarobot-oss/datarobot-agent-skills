# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from verify_mcp_tool import tool_name_for_deployment, assert_tool_present


def _tools():
    return [
        {"name": "weather", "meta": {"deployment_id": "depA"}},
        {"name": "scorer", "meta": {"deployment_id": "depB"}},
    ]


def test_finds_tool_by_deployment_id():
    assert tool_name_for_deployment("depB", _tools()) == "scorer"


def test_returns_none_when_absent():
    assert tool_name_for_deployment("depZ", _tools()) is None


def test_assert_present_true_false():
    assert assert_tool_present("depA", _tools()) is True
    assert assert_tool_present("depZ", _tools()) is False
