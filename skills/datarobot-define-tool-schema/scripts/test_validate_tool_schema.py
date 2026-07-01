# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from validate_tool_schema import main, validate_tool_schema


def test_data_nested_string_leaves_pass():
    schema = {"type": "object", "properties": {"data": {"type": "object",
        "properties": {"payload": {"type": "object",
            "properties": {"csv": {"type": "string"}}}}}}}
    assert validate_tool_schema(schema) == []


def test_data_non_string_leaf_rejected():
    schema = {"type": "object", "properties": {"data": {"type": "object",
        "properties": {"count": {"type": "integer"}}}}}
    errors = validate_tool_schema(schema)
    assert any("must be type 'string'" in e for e in errors)


def test_data_array_rejected():
    schema = {"type": "object", "properties": {"data": {"type": "object",
        "properties": {"rows": {"type": "array", "items": {"type": "string"}}}}}}
    errors = validate_tool_schema(schema)
    assert any("must not contain arrays" in e for e in errors)


def test_data_top_level_string_ok():
    # the predictive CSV fallback: data is a plain string
    schema = {"type": "object", "properties": {"data": {"type": "string"}},
              "required": ["data"]}
    assert validate_tool_schema(schema) == []


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


def test_path_params_as_array_type_rejected():
    """Fix #1: path_params declared as array (not object) must be rejected."""
    schema = {
        "type": "object",
        "properties": {
            "path_params": {"type": "array"},
        },
    }
    errors = validate_tool_schema(schema)
    assert errors, "Expected errors when path_params has type array"


def test_main_empty_schema_returns_1_allow_empty_returns_0():
    """main() returns 1 for empty schema; 0 when --allow-empty is passed."""
    empty_schema_json = '{"type":"object","properties":{}}'
    assert main(["prog", "--schema", empty_schema_json]) == 1
    assert main(["prog", "--schema", empty_schema_json, "--allow-empty"]) == 0


def test_main_valid_schema_returns_0():
    """main() returns 0 for a valid schema passed via --schema."""
    valid_schema_json = (
        '{"type":"object","properties":{"json":{"type":"object","properties":'
        '{"text":{"type":"string"}}}}}'
    )
    assert main(["prog", "--schema", valid_schema_json]) == 0
