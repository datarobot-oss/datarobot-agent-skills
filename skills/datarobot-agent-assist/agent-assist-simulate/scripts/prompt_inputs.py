#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic formatting for role-specific subagent input packages."""

from contracts import AgentSpec


def format_tools(spec: AgentSpec) -> str:
    """Render tool definitions consistently for scenario-generator prompts."""
    lines = []
    for tool in spec.tools:
        inputs = ", ".join(
            f"{argument.arg_name}: {argument.type}" for argument in tool.inputs
        )
        outputs = ", ".join(
            f"{argument.arg_name}: {argument.type}" for argument in tool.out
        )
        lines.append(f"- {tool.function_name}({inputs}) -> ({outputs})")
    return "\n".join(lines) if lines else "(no tools)"
