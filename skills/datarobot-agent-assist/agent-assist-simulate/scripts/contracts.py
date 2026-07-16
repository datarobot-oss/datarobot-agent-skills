#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validated data contracts shared by swarm simulation orchestrators."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    is_readonly: bool = False


class AgentSpec(BaseModel):
    model: str | None = None
    system_prompt: str | None = None
    tools: list[ToolDef] = []
    examples: list[str] = []


FailureSeverity = Literal["low", "medium", "high", "critical"]
CoverageMode = Literal["simulated", "selective_e2e"]


def _default_fail_on() -> list[FailureSeverity]:
    return ["high", "critical"]


class PersonaConfig(StrictOutput):
    description: str = Field(min_length=1)


class GroundingConfig(StrictOutput):
    context_path: str | None = None

    @field_validator("context_path")
    @classmethod
    def require_relative_context_path(cls, value: str | None) -> str | None:
        if value is not None and Path(value).is_absolute():
            raise ValueError("grounding context_path must be relative")
        return value


class EvaluationConfig(StrictOutput):
    mode: Literal["standard", "scored"] = "standard"
    fail_on: list[FailureSeverity] = Field(default_factory=_default_fail_on)


class ConvergenceConfig(StrictOutput):
    max_iterations: int = Field(default=3, ge=0)


class TurnLimits(StrictOutput):
    attack: int = Field(default=6, ge=1)
    behavior: int = Field(default=3, ge=1)
    persistence: int = Field(default=6, ge=1)

    def for_track(self, track: str) -> int:
        return int(getattr(self, track))


class RequestedScope(StrictOutput):
    tools: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)


class ExecutionConfig(StrictOutput):
    mode: CoverageMode = "simulated"
    requested_scope: RequestedScope = Field(default_factory=RequestedScope)


class SimulationConfig(StrictOutput):
    schema_version: Literal[1] = 1
    persona: PersonaConfig
    grounding: GroundingConfig = Field(default_factory=GroundingConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    convergence: ConvergenceConfig = Field(default_factory=ConvergenceConfig)
    turn_limits: TurnLimits = Field(default_factory=TurnLimits)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    model: str | None = None


class Scenario(BaseModel):
    scenario_id: str | None = Field(default=None, pattern=r"^scn_[0-9a-f]{12}$")
    name: str
    track: Literal["attack", "behavior", "persistence"]
    capability_targeted: str | None = None
    turns: list[str]
    expected_safe_behavior: str
    breach_indicators: list[str]
    max_turns: int = 6


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
    fixture_history: list[ToolFixture]
    turns_run: int = Field(ge=0)


class EvaluationResult(StrictOutput):
    outcome: Literal["passed", "breach"]
    severity: Literal["none", "low", "medium", "high", "critical"]
    reason: str
    evidence: list[str]

    @model_validator(mode="after")
    def validate_verdict(self) -> "EvaluationResult":
        """Require internally consistent evaluator evidence."""
        if self.outcome == "breach" and not self.evidence:
            raise ValueError("breach outcomes require at least one evidence item")
        if self.outcome == "breach" and self.severity == "none":
            raise ValueError("breach outcomes require a non-none severity")
        if self.outcome == "passed" and self.severity != "none":
            raise ValueError("passed outcomes require none severity")
        return self


class FixProposal(StrictOutput):
    description: str
    system_prompt_patch: str
    reasoning: str
    addresses_scenarios: list[str] = Field(min_length=1)


class StructuralDiagnosis(StrictOutput):
    remaining_risk: str = Field(min_length=1)
    structural_recommendation: str = Field(min_length=1)
    function_hint: str | None = None

    @field_validator("function_hint")
    @classmethod
    def normalize_function_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ScenarioResult(BaseModel):
    scenario: Scenario
    status: Literal["passed", "breach", "error", "exhausted"]
    breach_detected: bool
    breach_reason: str | None = None
    transcript: list[TranscriptEntry]
    turns_run: int
    attempted_tool_calls: list[AttemptedToolCall] = Field(default_factory=list)
    fixture_history: list[ToolFixture] = Field(default_factory=list)
    severity: Literal["none", "low", "medium", "high", "critical"] | None = None
    evidence: list[str] = Field(default_factory=list)
    evaluation_reason: str | None = None
    structural_diagnosis: StructuralDiagnosis | None = None


class SwarmTask(StrictOutput):
    scenario_id: str = Field(pattern=r"^scn_[0-9a-f]{12}$")
    scenario_name: str
    track: str
    run_dir: str
    role: Literal["runner", "fixture", "evaluator"]
    input_path: str
    response_path: str


class SwarmPreparation(StrictOutput):
    coverage_mode: CoverageMode
    tasks: list[SwarmTask]
    warnings: list[str] = Field(default_factory=list)


class SwarmResults(StrictOutput):
    coverage_mode: CoverageMode
    scenarios: list[ScenarioResult]


class ConvergenceTask(StrictOutput):
    task_id: str = Field(pattern=r"^(fix|diag)_[0-9a-f]{12}$")
    role: Literal["fixer", "diagnoser"]
    scenario_ids: list[str] = Field(min_length=1)
    input_path: str
    response_path: str


class ConvergencePreparation(StrictOutput):
    status: Literal["awaiting_fixers", "rerunning", "awaiting_diagnosers", "complete"]
    state_path: str
    tasks: list[ConvergenceTask | SwarmTask] = Field(default_factory=list)


class PromptPatchRecord(StrictOutput):
    cluster_id: str
    iteration: int = Field(ge=1)
    timestamp: str
    description: str
    system_prompt_patch: str
    reasoning: str
    addresses_scenarios: list[str] = Field(min_length=1)
    prompt_hash_before: str
    prompt_hash_after: str


class ConvergenceFailure(StrictOutput):
    task_id: str = Field(pattern=r"^(fix|diag)_[0-9a-f]{12}$")
    role: Literal["fixer", "diagnoser"]
    scenario_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    timestamp: str


class NativeReportSummary(StrictOutput):
    ready: bool
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    breached: int = Field(ge=0)
    exhausted: int = Field(ge=0)
    errored: int = Field(ge=0)
    convergence_failures: int = Field(ge=0)
    patches_applied: int = Field(ge=0)
    report_path: str


def confirm_scenario(proposal: ScenarioProposal) -> Scenario:
    """Create an authoritative scenario with a stable content-derived ID."""
    content = proposal.model_dump(mode="json")
    canonical = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return Scenario(scenario_id=f"scn_{digest}", **content)
