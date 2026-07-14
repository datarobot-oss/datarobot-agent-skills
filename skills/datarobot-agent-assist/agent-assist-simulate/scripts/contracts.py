#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validated data contracts shared by swarm simulation orchestrators."""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

TranscriptEntry = dict[str, Any]


class ToolInput(BaseModel):
    arg_name: str
    type: str


class ToolDef(BaseModel):
    function_name: str
    inputs: list[ToolInput] = []
    out: list[ToolInput] = []
    description: str = ""


class AgentSpec(BaseModel):
    model: str | None = None
    system_prompt: str | None = None
    tools: list[ToolDef] = []
    examples: list[str] = []


class Scenario(BaseModel):
    name: str
    track: Literal["attack", "behavior", "persistence"]
    capability_targeted: str | None = None
    turns: list[str]
    expected_safe_behavior: str
    breach_indicators: list[str]
    max_turns: int = 6


class ScenarioList(BaseModel):
    scenarios: list[Scenario]


class ScenarioResult(BaseModel):
    scenario: Scenario
    status: Literal["passed", "breach", "error", "exhausted"]
    breach_detected: bool
    breach_reason: str | None = None
    transcript: list[TranscriptEntry]
    turns_run: int
    structural_diagnosis: str | None = None


@dataclass
class Fix:
    scenario_name: str
    description: str
    system_prompt_patch: str
    reasoning: str
    addresses_scenarios: list[str] = field(default_factory=list)


@dataclass
class ConvergenceResult:
    resolved: list[ScenarioResult] = field(default_factory=list)
    exhausted: list[ScenarioResult] = field(default_factory=list)
    errors: list[ScenarioResult] = field(default_factory=list)
    patches_applied: list[Fix] = field(default_factory=list)
    final_system_prompt: str = ""
