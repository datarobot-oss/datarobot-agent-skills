#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate a model-metadata.yaml `inputSchema` against datarobot-genai's rules.

Usage:
    python validate_tool_schema.py path/to/model-metadata.yaml
    python validate_tool_schema.py path/to/model-metadata.yaml --allow-empty
    python validate_tool_schema.py --schema '{"type":"object",...}'
"""

import json
import sys
from typing import Any

ALLOWED_KEYS = {"path_params", "query_params", "data", "json"}
FLAT_KEYS = {"path_params", "query_params"}


def _is_flat_object(prop: dict[str, Any]) -> bool:
    """A flat object: every property is a JSON primitive (no object/array)."""
    if prop.get("type") == "array":
        return False
    for sub in (prop.get("properties") or {}).values():
        if sub.get("type") in ("object", "array"):
            return False
    return True


def _data_leaf_errors(prop: dict[str, Any], path: str = "data") -> list[str]:
    """`data` (form/raw body) allows nested objects, but every leaf must be a
    string and arrays are not allowed (form encoding does not preserve types)."""
    errors: list[str] = []
    ptype = prop.get("type")
    if ptype == "array":
        errors.append(f"'{path}' must not contain arrays ('data' is form-encoded)")
        return errors
    if ptype == "object":
        for name, sub in (prop.get("properties") or {}).items():
            errors.extend(_data_leaf_errors(sub, f"{path}.{name}"))
        return errors
    if ptype is not None and ptype != "string":
        errors.append(f"'{path}' leaf values must be type 'string' (found '{ptype}')")
    return errors


def validate_tool_schema(schema: Any, allow_empty: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["schema must be a JSON object"]
    props = schema.get("properties") or {}
    if not props:
        if not allow_empty:
            errors.append(
                "schema has no properties; empty schemas are rejected unless "
                "MCP_SERVER_TOOL_REGISTRATION_ALLOW_EMPTY_SCHEMA=true"
            )
        return errors
    for key, prop in props.items():
        if key not in ALLOWED_KEYS:
            errors.append(
                f"top-level key '{key}' is not allowed; only {sorted(ALLOWED_KEYS)} are permitted"
            )
            continue
        if key in FLAT_KEYS and not _is_flat_object(prop):
            errors.append(
                f"'{key}' must be a flat object (primitive properties only, no nested object/array)"
            )
        if key == "data":
            errors.extend(_data_leaf_errors(prop))
    return errors


def _load(path: str) -> Any:
    import yaml  # local import; only needed for the file path mode

    with open(path) as fh:
        meta = yaml.safe_load(fh)
    return meta.get("inputSchema", meta)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--allow-empty"]
    allow_empty = "--allow-empty" in argv[1:]
    if len(args) >= 2 and args[0] == "--schema":
        schema = json.loads(args[1])
    elif len(args) >= 1:
        schema = _load(args[0])
    else:
        print(__doc__ or "")
        return 2
    errors = validate_tool_schema(schema, allow_empty=allow_empty)
    if errors:
        print("INVALID inputSchema:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("inputSchema is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
