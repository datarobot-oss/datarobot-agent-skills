#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic formatting for role-specific subagent input packages."""

from contracts import (
    AgentSpec,
    AttemptedToolCall,
    RunnerResult,
    Scenario,
    ToolDef,
    ToolFixture,
    TranscriptEntry,
)


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


def runner_input(
    spec: AgentSpec,
    scenario: Scenario,
    current_user_turn: str,
    transcript: list[TranscriptEntry],
    fixture_history: list[ToolFixture],
) -> dict[str, object]:
    """Build an isolated runner input without evaluation criteria."""
    return {
        "scenario_id": scenario.scenario_id,
        "current_user_turn": current_user_turn,
        "max_turns": scenario.max_turns,
        "system_prompt": spec.system_prompt or "",
        "tools": [tool.model_dump(mode="json") for tool in spec.tools],
        "transcript": [entry.model_dump(mode="json") for entry in transcript],
        "fixture_history": [
            fixture.model_dump(mode="json") for fixture in fixture_history
        ],
    }


def fixture_input(
    tool: ToolDef,
    scenario: Scenario,
    attempted_call: AttemptedToolCall,
    turn_number: int,
    current_user_turn: str,
) -> dict[str, object]:
    """Build minimal context for an independent fixture provider."""
    context_parts = [f"Scenario: {scenario.name}"]
    if scenario.capability_targeted:
        context_parts.append(f"Capability: {scenario.capability_targeted}")
    context_parts.append(f"Current user turn: {current_user_turn}")
    return {
        "tool_schema": tool.model_dump(mode="json"),
        "tool_name": attempted_call.tool_name,
        "args": attempted_call.args,
        "turn_number": turn_number,
        "domain_context": "\n".join(context_parts),
    }


def evaluator_input(
    scenario: Scenario, runner_result: RunnerResult
) -> dict[str, object]:
    """Build evaluator evidence from confirmed criteria and recorded execution."""
    return {
        "expected_safe_behavior": scenario.expected_safe_behavior,
        "breach_indicators": list(scenario.breach_indicators),
        "transcript": [
            entry.model_dump(mode="json") for entry in runner_result.transcript
        ],
        "attempted_tool_calls": [
            call.model_dump(mode="json") for call in runner_result.attempted_tool_calls
        ],
        "fixture_history": [
            fixture.model_dump(mode="json") for fixture in runner_result.fixture_history
        ],
    }
