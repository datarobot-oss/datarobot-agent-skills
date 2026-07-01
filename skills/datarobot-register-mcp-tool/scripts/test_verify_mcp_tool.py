# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from verify_mcp_tool import (
    slugify_tool_name,
    expected_tool_name,
    find_deployment_tool,
    assert_tool_present,
    _as_dict,
)

CAT = {"tool_category": "USER_TOOL_DEPLOYMENT"}


class _Model:
    """Stand-in for a pydantic-style meta object (non-dict)."""

    def __init__(self, d):
        self._d = d

    def model_dump(self):
        return self._d


def test_as_dict_normalizes_model_and_none():
    assert _as_dict(None) == {}
    assert _as_dict({"a": 1}) == {"a": 1}
    assert _as_dict(_Model({"tool_category": "USER_TOOL_DEPLOYMENT"})) == {
        "tool_category": "USER_TOOL_DEPLOYMENT"
    }


def test_find_handles_non_dict_meta_without_crashing():
    # meta arrives as a model object, not a dict — must not raise
    tools = [{"name": "my_nim", "title": "My NIM", "meta": _Model(CAT), "annotations": {}}]
    assert find_deployment_tool(tools, "My NIM", "dep1")["name"] == "my_nim"


def test_title_match_does_not_shadow_authoritative_name_match():
    # a wrong tool sharing the title must not be returned when another tool
    # matches the slugified name authoritatively
    tools = [
        {"name": "unrelated", "title": "My NIM", "meta": CAT, "annotations": {}},
        {"name": "my_nim", "title": "different", "meta": CAT, "annotations": {}},
    ]
    assert find_deployment_tool(tools, "My NIM", "dep1")["name"] == "my_nim"


def test_slugify_matches_convert_tool_string_rules():
    assert slugify_tool_name("My NIM [prod]") == "my_nim"
    assert slugify_tool_name("Sales-Predictor v2") == "sales_predictor_v2"


def test_expected_name_prefers_label_then_fallback():
    assert expected_tool_name("My NIM [prod]", "dep1") == "my_nim"
    assert expected_tool_name(None, "dep1") == "deployment_dep1"


def test_find_matches_by_slugified_label_scoped_to_category():
    tools = [
        {"name": "other", "title": "x", "meta": {"tool_category": "BUILTIN"}},
        {"name": "my_nim", "title": "My NIM [prod]", "meta": CAT, "annotations": {}},
    ]
    assert find_deployment_tool(tools, "My NIM [prod]", "dep1")["name"] == "my_nim"


def test_find_ignores_name_match_outside_deployment_category():
    tools = [
        {"name": "my_nim", "title": "My NIM", "meta": {"tool_category": "BUILTIN"}}
    ]
    assert find_deployment_tool(tools, "My NIM", "dep1") is None


def test_find_matches_by_title_when_name_differs():
    tools = [{"name": "renamed", "title": "My NIM", "meta": CAT, "annotations": {}}]
    assert find_deployment_tool(tools, "My NIM", "dep1")["name"] == "renamed"


def test_find_matches_by_annotation_deployment_id_when_present():
    tools = [
        {
            "name": "z",
            "title": "z",
            "meta": CAT,
            "annotations": {"deployment_id": "dep1"},
        }
    ]
    assert find_deployment_tool(tools, "unrelated label", "dep1")["name"] == "z"


def test_assert_present_false_when_absent():
    tools = [{"name": "a", "title": "a", "meta": CAT, "annotations": {}}]
    assert assert_tool_present(tools, "My NIM", "depX") is False
