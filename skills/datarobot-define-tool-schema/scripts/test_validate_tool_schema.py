# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from validate_tool_schema import validate_tool_schema


def test_valid_json_body_schema_passes():
    schema = {
        "type": "object",
        "properties": {
            "json": {"type": "object", "properties": {"text": {"type": "string"}}}
        },
        "required": ["json"],
    }
    assert validate_tool_schema(schema) == []


def test_unknown_top_level_key_rejected():
    schema = {"type": "object", "properties": {"body": {"type": "object"}}}
    errors = validate_tool_schema(schema)
    assert any("body" in e and "not allowed" in e for e in errors)


def test_empty_schema_rejected_unless_allowed():
    schema = {"type": "object", "properties": {}}
    assert validate_tool_schema(schema, allow_empty=False) != []
    assert validate_tool_schema(schema, allow_empty=True) == []


def test_path_params_must_be_flat():
    schema = {
        "type": "object",
        "properties": {
            "path_params": {
                "type": "object",
                "properties": {"nested": {"type": "object"}},
            }
        },
    }
    errors = validate_tool_schema(schema)
    assert any("path_params" in e and "flat" in e for e in errors)


def test_query_params_must_be_flat():
    schema = {
        "type": "object",
        "properties": {
            "query_params": {
                "type": "object",
                "properties": {
                    "nested": {"type": "array", "items": {"type": "object"}}
                },
            }
        },
    }
    errors = validate_tool_schema(schema)
    assert any("query_params" in e for e in errors)
