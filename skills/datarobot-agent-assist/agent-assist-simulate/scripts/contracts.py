#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validated data contracts shared by swarm simulation orchestrators."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictOutput(BaseModel):
    """Base contract for untrusted native-subagent output."""

    model_config = ConfigDict(extra="forbid")


class TranscriptEntry(StrictOutput):
    role: Literal["user", "assistant"]
    content: str


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
    scenario_id: str | None = Field(default=None, pattern=r"^scn_[0-9a-f]{12}$")
    name: str
    track: Literal["attack", "behavior", "persistence"]
    capability_targeted: str | None = None
    turns: list[str]
    expected_safe_behavior: str
    breach_indicators: list[str]
    max_turns: int = 6


class ScenarioList(BaseModel):
    scenarios: list[Scenario]


class ScenarioProposal(StrictOutput):
    name: str
    track: Literal["attack", "behavior", "persistence"]
    capability_targeted: str | None = None
    turns: list[str] = Field(min_length=1)
    expected_safe_behavior: str
    breach_indicators: list[str]
    max_turns: int = Field(default=6, ge=1)


class ScenarioProposalList(StrictOutput):
    scenarios: list[ScenarioProposal] = Field(min_length=1)


class AttemptedToolCall(StrictOutput):
    tool_name: str
    args: dict[str, Any]


class ToolFixture(StrictOutput):
    tool_name: str
    args: dict[str, Any]
    return_value: Any


class AssistantResponseAction(StrictOutput):
    type: Literal["assistant_response"]
    content: str


class ToolCallAction(StrictOutput):
    type: Literal["tool_call"]
    tool_call: AttemptedToolCall


RunnerAction = Annotated[
    AssistantResponseAction | ToolCallAction, Field(discriminator="type")
]


class RunnerResult(StrictOutput):
    scenario_id: str = Field(pattern=r"^scn_[0-9a-f]{12}$")
    transcript: list[TranscriptEntry]
    attempted_tool_calls: list[AttemptedToolCall]
    turns_run: int = Field(ge=0)


class EvaluationResult(StrictOutput):
    outcome: Literal["passed", "breach"]
    severity: Literal["none", "low", "medium", "high", "critical"]
    reason: str
    evidence: list[str]


class FixProposal(StrictOutput):
    description: str
    system_prompt_patch: str
    reasoning: str
    addresses_scenarios: list[str] = Field(min_length=1)


class StructuralDiagnosis(StrictOutput):
    remaining_risk: str
    structural_recommendation: str
    function_hint: str | None = None


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


def confirm_scenario(proposal: ScenarioProposal) -> Scenario:
    """Create an authoritative scenario with a stable content-derived ID."""
    content = proposal.model_dump(mode="json")
    canonical = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return Scenario(scenario_id=f"scn_{digest}", **content)


def fix_from_proposal(proposal: FixProposal) -> Fix:
    """Convert validated fixer output into the Python-owned audit record."""
    return Fix(
        scenario_name=proposal.addresses_scenarios[0],
        description=proposal.description,
        system_prompt_patch=proposal.system_prompt_patch,
        reasoning=proposal.reasoning,
        addresses_scenarios=list(proposal.addresses_scenarios),
    )
