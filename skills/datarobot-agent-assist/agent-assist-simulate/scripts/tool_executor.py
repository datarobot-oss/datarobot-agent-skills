#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Real tool executor for selective E2E simulation.

Reads a fixture input package, calls the real tool function from the user's
tools.py, and writes a ToolFixture-shaped JSON response to response_path.
Used in place of the fixture LLM worker when execution.mode is selective_e2e.
"""

import argparse
import asyncio
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path


def _reexec_into_tools_venv(tools_path: Path) -> None:
    """Re-run this script under the nearest ``.venv/bin/python3``.

    Stops walking at ``agent_spec.md`` or ``.git`` so a parent repo venv is
    not used. No-op when already running inside that venv, or when none exists.
    """
    start = tools_path.resolve().parent
    for parent in [start, *start.parents]:
        python = parent / ".venv" / "bin" / "python3"
        if python.is_file():
            if Path(sys.prefix).resolve() != python.parent.parent.resolve():
                os.execv(
                    str(python),
                    [str(python), str(Path(__file__).resolve()), *sys.argv[1:]],
                )
            return
        if (parent / "agent_spec.md").is_file() or (parent / ".git").exists():
            return


def _load_tools_module(tools_path: Path) -> object:
    if not tools_path.is_file():
        print(f"tools-path not found: {tools_path}", file=sys.stderr)
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("_user_tools", tools_path)
    if spec is None or spec.loader is None:
        print(f"cannot load module from: {tools_path}", file=sys.stderr)
        sys.exit(1)
    module = importlib.util.module_from_spec(spec)
    project_dir = str(tools_path.parent)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        print(f"import error in {tools_path}: {exc}", file=sys.stderr)
        sys.exit(1)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-path", required=True, type=Path)
    parser.add_argument("--response-path", required=True, type=Path)
    parser.add_argument("--tools-path", required=True, type=Path)
    parser.add_argument(
        "--readonly-tools",
        required=True,
        help="comma-separated list of function names approved for real execution",
    )
    args = parser.parse_args()
    _reexec_into_tools_venv(args.tools_path)

    readonly_tools = {t.strip() for t in args.readonly_tools.split(",") if t.strip()}

    try:
        package = json.loads(args.input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read input-path: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(package, dict):
        print(
            f"input package must be a JSON object, got {type(package).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)

    tool_name: str = package.get("tool_name", "")
    call_args: dict[str, object] = package.get("args", {})

    if not tool_name:
        print("input package missing tool_name", file=sys.stderr)
        sys.exit(1)

    if tool_name not in readonly_tools:
        print(
            f"tool '{tool_name}' is not in the approved readonly set: {sorted(readonly_tools)}",
            file=sys.stderr,
        )
        sys.exit(1)

    module = _load_tools_module(args.tools_path)

    fn = getattr(module, tool_name, None)
    if fn is None:
        print(f"function not found in {args.tools_path}: {tool_name}", file=sys.stderr)
        sys.exit(1)

    try:
        if callable(fn):
            result = fn(**call_args)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            if hasattr(result, "model_dump"):
                result = result.model_dump()
            return_value = result
        elif hasattr(fn, "invoke"):
            return_value = fn.invoke(call_args)
        else:
            print(f"{tool_name} is not callable", file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        print(f"{tool_name} raised {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    response = {"tool_name": tool_name, "args": call_args, "return_value": return_value}
    try:
        payload = json.dumps(response, ensure_ascii=False, indent=2)
    except TypeError as exc:
        print(
            f"{tool_name} return value is not JSON-serializable: {exc}", file=sys.stderr
        )
        sys.exit(1)
    args.response_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.response_path.with_name(f".{args.response_path.name}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, args.response_path)


if __name__ == "__main__":
    main()
