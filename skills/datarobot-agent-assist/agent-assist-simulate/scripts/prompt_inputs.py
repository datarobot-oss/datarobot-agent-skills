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


def attack_input(spec: AgentSpec) -> dict[str, object]:
    """Build the minimal attack-generator input package."""
    return {
        "system_prompt": spec.system_prompt or "",
        "tools": format_tools(spec),
    }


def behavior_input(
    spec: AgentSpec, user_persona: str, grounding_context: str | None
) -> dict[str, object]:
    """Build the minimal behavior-generator input package."""
    return {
        "system_prompt": spec.system_prompt or "",
        "user_persona": user_persona,
        "examples": list(spec.examples),
        "grounding_context": grounding_context,
    }


def persistence_input(
    spec: AgentSpec, implementation_context: str | None
) -> dict[str, object]:
    """Build the minimal persistence-generator input package."""
    return {
        "system_prompt": spec.system_prompt or "",
        "tools": format_tools(spec),
        "implementation_context": implementation_context or "",
    }
