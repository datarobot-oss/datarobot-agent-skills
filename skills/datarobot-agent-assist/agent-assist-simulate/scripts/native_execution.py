#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Advance one harness-native scenario through runner, fixture, and evaluator roles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter, ValidationError

from artifacts import _one_line, load_criteria, load_json, load_spec, write_json
from swarm_contracts import (
    AgentSpec,
    AssistantResponseAction,
    AttemptedToolCall,
    EvaluationResult,
    RunnerAction,
    RunnerResult,
    Scenario,
    ScenarioResult,
    StrictOutput,
    ToolCallAction,
    ToolFixture,
    TranscriptEntry,
)
from prompt_inputs import evaluator_input, fixture_input, runner_input

Role = Literal["runner", "fixture", "evaluator"]
JudgeMode = Literal["standard", "scored"]
FailureSeverity = Literal["low", "medium", "high", "critical"]

MAX_TOOL_CALLS_PER_TURN = 5
MAX_FIXTURE_RETURN_BYTES = 50 * 1024
STATE_FILENAME = "run-state.json"
RESULT_FILENAME = "result.json"
RUNNER_ACTION_ADAPTER: TypeAdapter[RunnerAction] = TypeAdapter(RunnerAction)


def _default_fail_on() -> list[FailureSeverity]:
    return ["high", "critical"]


class NativeExecutionValidationError(ValueError):
    """Raised when the current worker returns invalid output."""

    def __init__(self, role: Role, reason: str) -> None:
        self.role = role
        self.reason = reason
        super().__init__(f"{role}: {reason}")


class NativeRunState(StrictOutput):
    """Deterministic working state for one scenario."""

    spec: AgentSpec
    scenario: Scenario
    judge_mode: JudgeMode = "standard"
    fail_on: list[FailureSeverity] = Field(default_factory=_default_fail_on)
    effective_max_turns: int = Field(ge=1)
    status: Literal["running", "complete", "error"] = "running"
    next_role: Role | None = "runner"
    turn_index: int = Field(default=0, ge=0)
    turns_run: int = Field(default=0, ge=0)
    tool_calls_this_turn: int = Field(default=0, ge=0)
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    attempted_tool_calls: list[AttemptedToolCall] = Field(default_factory=list)
    fixture_history: list[ToolFixture] = Field(default_factory=list)
    pending_tool_call: AttemptedToolCall | None = None
    include_active_user_in_evaluation: bool = False
    result: ScenarioResult | None = None


def initialize(
    spec_path: Path,
    criteria_path: Path,
    scenario_id: str,
    run_dir: Path,
    judge_mode: JudgeMode = "standard",
    fail_on: list[FailureSeverity] | None = None,
    turn_limit: int | None = None,
    fixture_history: list[ToolFixture] | None = None,
) -> dict[str, object]:
    """Initialize one scenario and write its first isolated runner input."""
    if (run_dir / STATE_FILENAME).exists() or (run_dir / RESULT_FILENAME).exists():
        raise ValueError(f"run already initialized: {run_dir}")
    spec = load_spec(spec_path)
    scenarios = load_criteria(criteria_path)
    matching = [
        scenario for scenario in scenarios if scenario.scenario_id == scenario_id
    ]
    if not matching:
        raise ValueError(f"scenario not found in confirmed criteria: {scenario_id}")
    scenario = matching[0]
    if not scenario.scenario_id:
        raise ValueError("confirmed scenario is missing scenario_id")
    if not scenario.turns:
        raise ValueError(f"scenario {scenario_id} has no user turns")
    if not spec.system_prompt:
        raise ValueError("agent spec is missing system_prompt")
    if turn_limit is not None and turn_limit < 1:
        raise ValueError("turn_limit must be at least 1")
    for fixture in fixture_history or []:
        _validate_fixture_size(fixture.return_value)

    state = NativeRunState(
        spec=spec,
        scenario=scenario,
        judge_mode=judge_mode,
        fail_on=fail_on or ["high", "critical"],
        effective_max_turns=min(scenario.max_turns, turn_limit or scenario.max_turns),
        fixture_history=list(fixture_history or []),
    )
    return _persist_next(state, run_dir)


def submit(run_dir: Path, response_path: Path) -> dict[str, object]:
    """Validate one worker response and advance to the next permitted state."""
    state = NativeRunState.model_validate(load_json(run_dir / STATE_FILENAME))
    if state.status != "running" or state.next_role is None:
        raise ValueError(f"run is already {state.status}")

    role = state.next_role
    try:
        response = load_json(response_path)
        if role == "runner":
            _apply_runner_action(state, response)
        elif role == "fixture":
            _apply_fixture(state, response)
        else:
            _apply_evaluation(state, response)
    except NativeExecutionValidationError:
        raise
    except (OSError, ValueError, ValidationError, TypeError) as exc:
        raise NativeExecutionValidationError(role, _one_line(exc)) from exc

    if state.result is not None:
        return _persist_terminal(state, run_dir)
    return _persist_next(state, run_dir)


def fail(run_dir: Path, reason: str) -> dict[str, object]:
    """Record a terminal external worker failure without overwriting a result."""
    state = NativeRunState.model_validate(load_json(run_dir / STATE_FILENAME))
    if state.status != "running" or state.next_role is None:
        raise ValueError(f"run is already {state.status}")
    role = state.next_role
    _record_execution_error(state, f"{role} worker failed: {reason}")
    return _persist_terminal(state, run_dir)


def _apply_runner_action(state: NativeRunState, response: object) -> None:
    action = RUNNER_ACTION_ADAPTER.validate_python(response)
    state.turns_run = max(state.turns_run, state.turn_index + 1)

    if isinstance(action, AssistantResponseAction):
        state.transcript.extend(
            [
                TranscriptEntry(role="user", content=_current_user_turn(state)),
                TranscriptEntry(role="assistant", content=action.content),
            ]
        )
        state.turn_index += 1
        state.tool_calls_this_turn = 0
        state.pending_tool_call = None
        if state.turn_index >= min(
            len(state.scenario.turns), state.effective_max_turns
        ):
            state.next_role = "evaluator"
        else:
            state.next_role = "runner"
        return

    if not isinstance(action, ToolCallAction):
        raise TypeError(f"unsupported runner action: {type(action).__name__}")

    attempted_call = action.tool_call
    state.attempted_tool_calls.append(attempted_call)
    state.tool_calls_this_turn += 1
    if state.tool_calls_this_turn > MAX_TOOL_CALLS_PER_TURN:
        _record_execution_error(
            state,
            f"runner exceeded {MAX_TOOL_CALLS_PER_TURN} tool calls in one user turn",
        )
        return

    matching_tool = next(
        (
            tool
            for tool in state.spec.tools
            if tool.function_name == attempted_call.tool_name
        ),
        None,
    )
    if matching_tool is None:
        state.include_active_user_in_evaluation = True
        state.pending_tool_call = None
        state.next_role = "evaluator"
        return

    state.pending_tool_call = attempted_call
    state.next_role = "fixture"


def _apply_fixture(state: NativeRunState, response: object) -> None:
    fixture = ToolFixture.model_validate(response)
    _validate_fixture_size(fixture.return_value)
    pending = state.pending_tool_call
    if pending is None:
        raise ValueError("fixture received without a pending tool call")
    if fixture.tool_name != pending.tool_name:
        raise ValueError(
            f"fixture tool_name {fixture.tool_name!r} does not match "
            f"attempted tool {pending.tool_name!r}"
        )
    if _canonical_json(fixture.args) != _canonical_json(pending.args):
        raise ValueError("fixture args do not exactly match attempted tool args")

    state.fixture_history.append(fixture)
    state.pending_tool_call = None
    state.next_role = "runner"


def _validate_fixture_size(value: object) -> None:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if len(encoded) > MAX_FIXTURE_RETURN_BYTES:
        raise ValueError(
            f"fixture return_value exceeds {MAX_FIXTURE_RETURN_BYTES} bytes"
        )


def _apply_evaluation(state: NativeRunState, response: object) -> None:
    evaluation = EvaluationResult.model_validate(response)
    breach = evaluation.outcome == "breach" and (
        state.judge_mode == "standard" or evaluation.severity in state.fail_on
    )
    runner_result = _runner_result(state)
    result = ScenarioResult(
        scenario=state.scenario,
        status="breach" if breach else "passed",
        breach_detected=breach,
        breach_reason=evaluation.reason if breach else None,
        transcript=runner_result.transcript,
        turns_run=runner_result.turns_run,
        attempted_tool_calls=runner_result.attempted_tool_calls,
        fixture_history=runner_result.fixture_history,
        severity=evaluation.severity,
        evidence=evaluation.evidence,
        evaluation_reason=evaluation.reason,
    )
    state.status = "complete"
    state.next_role = None
    state.result = result


def _record_execution_error(state: NativeRunState, reason: str) -> None:
    runner_result = _runner_result(state, include_active_user=True)
    state.status = "error"
    state.next_role = None
    state.pending_tool_call = None
    state.result = ScenarioResult(
        scenario=state.scenario,
        status="error",
        breach_detected=False,
        breach_reason=reason,
        transcript=runner_result.transcript,
        turns_run=runner_result.turns_run,
        attempted_tool_calls=runner_result.attempted_tool_calls,
        fixture_history=runner_result.fixture_history,
        evaluation_reason=reason,
    )


def _runner_result(
    state: NativeRunState, include_active_user: bool | None = None
) -> RunnerResult:
    transcript = list(state.transcript)
    should_include = (
        state.include_active_user_in_evaluation
        if include_active_user is None
        else include_active_user
    )
    if should_include and state.turn_index < len(state.scenario.turns):
        transcript.append(
            TranscriptEntry(role="user", content=_current_user_turn(state))
        )
    return RunnerResult(
        scenario_id=state.scenario.scenario_id or "",
        transcript=transcript,
        attempted_tool_calls=list(state.attempted_tool_calls),
        fixture_history=list(state.fixture_history),
        turns_run=state.turns_run,
    )


def _persist_next(state: NativeRunState, run_dir: Path) -> dict[str, object]:
    if state.next_role is None:
        raise ValueError("running state has no next role")
    input_path = run_dir / f"{state.next_role}-input.json"
    if state.next_role == "runner":
        package = runner_input(
            state.spec,
            state.scenario,
            state.effective_max_turns,
            _current_user_turn(state),
            state.transcript,
            state.fixture_history,
        )
    elif state.next_role == "fixture":
        pending = state.pending_tool_call
        if pending is None:
            raise ValueError("fixture state has no pending tool call")
        tool = next(
            tool for tool in state.spec.tools if tool.function_name == pending.tool_name
        )
        package = fixture_input(
            tool,
            state.scenario,
            pending,
            state.turn_index + 1,
            _current_user_turn(state),
        )
    else:
        package = evaluator_input(state.scenario, _runner_result(state))

    write_json(run_dir / STATE_FILENAME, state.model_dump(mode="json"))
    write_json(input_path, package)
    transition: dict[str, object] = {
        "status": "next",
        "scenario_id": state.scenario.scenario_id,
        "scenario_name": state.scenario.name,
        "run_dir": str(run_dir),
        "role": state.next_role,
        "input_path": str(input_path),
        "response_path": str(run_dir / "worker-output.json"),
    }
    if state.next_role in ("runner", "fixture"):
        total_turns = min(len(state.scenario.turns), state.effective_max_turns)
        transition["turn_number"] = state.turn_index + 1
        transition["total_turns"] = total_turns
    return transition


def _persist_terminal(state: NativeRunState, run_dir: Path) -> dict[str, object]:
    if state.result is None:
        raise ValueError(f"terminal {state.status} state has no result")
    result_path = run_dir / RESULT_FILENAME
    write_json(run_dir / STATE_FILENAME, state.model_dump(mode="json"))
    write_json(result_path, state.result.model_dump(mode="json"))
    display_status = state.result.status if state.status == "complete" else state.status
    response: dict[str, object] = {
        "status": display_status,
        "scenario_id": state.scenario.scenario_id,
        "run_dir": str(run_dir),
        "result_path": str(result_path),
    }
    if state.status == "error":
        response["reason"] = state.result.evaluation_reason or "execution failed"
    return response


def _current_user_turn(state: NativeRunState) -> str:
    if state.turn_index >= len(state.scenario.turns):
        raise ValueError("scenario has no remaining user turn")
    return state.scenario.turns[state.turn_index]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize_parser = subparsers.add_parser("initialize")
    initialize_parser.add_argument("spec", type=Path)
    initialize_parser.add_argument("--criteria", type=Path, required=True)
    initialize_parser.add_argument("--scenario-id", required=True)
    initialize_parser.add_argument("--run-dir", type=Path, required=True)
    initialize_parser.add_argument(
        "--judge-mode", choices=["standard", "scored"], default="standard"
    )
    initialize_parser.add_argument(
        "--fail-on",
        nargs="+",
        choices=["low", "medium", "high", "critical"],
        default=["high", "critical"],
    )
    initialize_parser.add_argument("--turn-limit", type=int)

    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("--run-dir", type=Path, required=True)
    submit_parser.add_argument("--response", type=Path, required=True)

    fail_parser = subparsers.add_parser("fail")
    fail_parser.add_argument("--run-dir", type=Path, required=True)
    fail_parser.add_argument("--reason", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the deterministic native-execution helper."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "initialize":
            transition = initialize(
                args.spec,
                args.criteria,
                args.scenario_id,
                args.run_dir,
                args.judge_mode,
                args.fail_on,
                args.turn_limit,
            )
        elif args.command == "submit":
            transition = submit(args.run_dir, args.response)
        else:
            transition = fail(args.run_dir, args.reason)
        print(json.dumps(transition, ensure_ascii=False))
        return 0
    except NativeExecutionValidationError as exc:
        print(
            f"role:{exc.role} validation failed: {exc.reason}",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, ValidationError) as exc:
        print(f"{args.command} failed: {_one_line(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
