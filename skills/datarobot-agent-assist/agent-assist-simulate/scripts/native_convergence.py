#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Initialize and advance harness-native convergence state."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from artifacts import (
    _one_line,
    _resolve_project_file,
    _resolve_under_root,
    _scenario_id,
    load_criteria,
    load_json,
    load_native_config,
    load_spec,
    write_json,
)
from swarm_contracts import (
    NativeReportSummary,
    Scenario,
    ScenarioResult,
    SimulationConfig,
    StrictOutput,
    SwarmResults,
)
from native_execution import RESULT_FILENAME, STATE_FILENAME as RUN_STATE_FILENAME
from native_execution import NativeRunState
from write_report import write_native_report

STATE_FILENAME = "state.json"


class NativeConvergenceState(StrictOutput):
    """Deterministic working state for native convergence."""

    schema_version: Literal[1] = 1
    status: Literal["open", "complete"]
    spec_path: str
    convergence_dir: str
    started_at: str
    completed_at: str | None = None
    actual_model: str | None = None
    config: SimulationConfig
    initial_results: SwarmResults
    latest_results: list[ScenarioResult]
    iteration_counts: dict[str, int]


def initialize(
    spec_path: Path,
    criteria_path: Path,
    config_path: Path,
    results_path: Path,
    convergence_dir: Path,
    actual_model: str | None = None,
) -> dict[str, object]:
    """Create convergence state and return breach evidence for the harness."""
    resolved_spec = spec_path.resolve()
    if not resolved_spec.is_file():
        raise ValueError(f"agent spec does not exist: {resolved_spec}")
    project_root = resolved_spec.parent
    resolved_criteria = _resolve_project_file(
        project_root, criteria_path, "evaluation criteria"
    )
    resolved_config = _resolve_project_file(
        project_root, config_path, "simulation config"
    )
    resolved_results = _resolve_project_file(
        project_root, results_path, "swarm results"
    )
    resolved_convergence_dir = _resolve_under_root(
        project_root, convergence_dir, "convergence directory"
    )
    state_path = resolved_convergence_dir / STATE_FILENAME
    if state_path.exists():
        raise ValueError(f"convergence already initialized: {state_path}")

    spec = load_spec(resolved_spec)
    if not spec.system_prompt:
        raise ValueError("agent spec is missing system_prompt")
    config, _ = load_native_config(resolved_config)
    criteria = load_criteria(resolved_criteria)
    initial_results = SwarmResults.model_validate(load_json(resolved_results))
    _validate_results_against_criteria(initial_results, criteria)

    latest_results = list(initial_results.scenarios)
    if config.convergence.max_iterations == 0:
        latest_results = [
            (
                result.model_copy(update={"status": "exhausted"})
                if result.status == "breach"
                else result
            )
            for result in latest_results
        ]

    iteration_counts = {_scenario_id(result.scenario): 0 for result in latest_results}

    has_breaches = any(r.status == "breach" for r in latest_results)
    state = NativeConvergenceState(
        status="open" if has_breaches else "complete",
        spec_path=str(resolved_spec),
        convergence_dir=str(resolved_convergence_dir),
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat()
        if not has_breaches
        else None,
        actual_model=actual_model,
        config=config,
        initial_results=initial_results,
        latest_results=latest_results,
        iteration_counts=iteration_counts,
    )
    write_json(state_path, state.model_dump(mode="json"))
    return _status_payload(state, resolved_convergence_dir)


def advance(
    spec_path: Path,
    convergence_dir: Path,
    rerun_pairs: list[tuple[str, Path]],
) -> dict[str, object]:
    """Read completed reruns, update iteration counts, return updated status."""
    resolved_spec = spec_path.resolve()
    if not resolved_spec.is_file():
        raise ValueError(f"agent spec does not exist: {resolved_spec}")
    project_root = resolved_spec.parent
    resolved_convergence_dir = _resolve_under_root(
        project_root, convergence_dir, "convergence directory"
    )
    state_path = resolved_convergence_dir / STATE_FILENAME
    state = NativeConvergenceState.model_validate(load_json(state_path))

    if state.status == "complete":
        raise ValueError("convergence is already complete")

    current_by_id = {
        _scenario_id(result.scenario): result for result in state.latest_results
    }
    max_iterations = state.config.convergence.max_iterations

    rerun_results: dict[str, ScenarioResult] = {}
    for scenario_id, run_dir in rerun_pairs:
        if scenario_id not in current_by_id:
            raise ValueError(f"unknown scenario_id in rerun: {scenario_id}")
        result_path = run_dir / RESULT_FILENAME
        run_state_path = run_dir / RUN_STATE_FILENAME
        if result_path.is_file():
            result = ScenarioResult.model_validate(load_json(result_path))
            rerun_results[scenario_id] = result
        elif run_state_path.is_file():
            run_state = NativeRunState.model_validate(load_json(run_state_path))
            if run_state.status == "running":
                raise ValueError(
                    f"{scenario_id}: rerun still running; expected role {run_state.next_role}"
                )
            raise ValueError(f"{scenario_id}: terminal rerun state has no result")
        else:
            raise ValueError(f"{scenario_id}: rerun was never initialized")

    latest: list[ScenarioResult] = []
    for result in state.latest_results:
        sid = _scenario_id(result.scenario)
        if sid in rerun_results:
            replacement = rerun_results[sid]
            state.iteration_counts[sid] = state.iteration_counts.get(sid, 0) + 1
            if (
                replacement.status == "breach"
                and state.iteration_counts[sid] >= max_iterations
            ):
                replacement = replacement.model_copy(update={"status": "exhausted"})
            latest.append(replacement)
        else:
            latest.append(result)

    state.latest_results = latest

    if not any(r.status == "breach" for r in state.latest_results):
        state.status = "complete"
        state.completed_at = datetime.now(timezone.utc).isoformat()

    write_json(state_path, state.model_dump(mode="json"))
    return _status_payload(state, resolved_convergence_dir)


def report(
    spec_path: Path,
    convergence_dir: Path,
    output_path: Path,
) -> NativeReportSummary:
    """Validate completed convergence and render the authoritative native report."""
    resolved_spec = spec_path.resolve()
    if not resolved_spec.is_file():
        raise ValueError(f"agent spec does not exist: {resolved_spec}")
    project_root = resolved_spec.parent
    resolved_convergence_dir = _resolve_under_root(
        project_root, convergence_dir, "convergence directory"
    )
    resolved_output = _resolve_under_root(
        project_root, output_path, "evaluation report"
    )
    state = NativeConvergenceState.model_validate(
        load_json(resolved_convergence_dir / STATE_FILENAME)
    )
    if Path(state.spec_path) != resolved_spec:
        raise ValueError("convergence state belongs to a different agent spec")
    if state.status != "complete":
        raise ValueError(f"convergence is not complete: {state.status}")
    return write_native_report(state, resolved_output)


def _status_payload(
    state: NativeConvergenceState,
    convergence_dir: Path,
) -> dict[str, object]:
    breaches = []
    exhausted = []
    passed = []
    for result in state.latest_results:
        sid = _scenario_id(result.scenario)
        iteration = state.iteration_counts.get(sid, 0)
        base: dict[str, object] = {
            "scenario_id": sid,
            "scenario_name": result.scenario.name,
            "track": result.scenario.track,
            "breach_reason": result.breach_reason or result.evaluation_reason,
            "transcript": [e.model_dump() for e in result.transcript],
            "breach_indicators": result.scenario.breach_indicators,
            "iteration": iteration,
        }
        if result.status == "breach":
            next_iter = iteration + 1
            base["suggested_rerun_dir"] = str(
                convergence_dir / "runs" / sid / f"iteration-{next_iter}"
            )
            breaches.append(base)
        elif result.status == "exhausted":
            exhausted.append(base)
        elif result.status == "passed":
            passed.append(sid)

    return {
        "status": state.status,
        "breaches": breaches,
        "exhausted": exhausted,
        "passed": passed,
    }


def _validate_results_against_criteria(
    results: SwarmResults, criteria: list[Scenario]
) -> None:
    if len(results.scenarios) != len(criteria):
        raise ValueError(
            "swarm results count does not match confirmed evaluation criteria"
        )
    for index, (result, scenario) in enumerate(
        zip(results.scenarios, criteria, strict=True)
    ):
        if result.scenario.model_dump(mode="json") != scenario.model_dump(mode="json"):
            raise ValueError(
                f"swarm result at index {index} differs from confirmed criteria"
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize_parser = subparsers.add_parser("initialize")
    initialize_parser.add_argument("spec", type=Path)
    initialize_parser.add_argument(
        "--criteria", type=Path, default=Path("evaluation_criteria.md")
    )
    initialize_parser.add_argument(
        "--config", type=Path, default=Path("agent_config.yaml")
    )
    initialize_parser.add_argument(
        "--results", type=Path, default=Path(".datarobot/swarm/results.json")
    )
    initialize_parser.add_argument(
        "--convergence-dir",
        type=Path,
        default=Path(".datarobot/swarm/convergence"),
    )
    initialize_parser.add_argument("--actual-model")

    advance_parser = subparsers.add_parser("advance")
    advance_parser.add_argument("spec", type=Path)
    advance_parser.add_argument(
        "--convergence-dir",
        type=Path,
        default=Path(".datarobot/swarm/convergence"),
    )
    advance_parser.add_argument(
        "--rerun",
        dest="reruns",
        action="append",
        default=[],
        metavar="SCENARIO_ID:RUN_DIR",
        help="scenario_id:run_dir pair for a completed rerun (repeatable)",
    )

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("spec", type=Path)
    report_parser.add_argument(
        "--convergence-dir",
        type=Path,
        default=Path(".datarobot/swarm/convergence"),
    )
    report_parser.add_argument("--output", type=Path, default=Path("eval_report.md"))
    return parser


def _parse_reruns(raw: list[str]) -> list[tuple[str, Path]]:
    pairs = []
    for item in raw:
        if ":" not in item:
            raise ValueError(f"--rerun must be scenario_id:run_dir, got: {item!r}")
        scenario_id, run_dir = item.split(":", 1)
        if not scenario_id or not run_dir:
            raise ValueError(f"--rerun must be scenario_id:run_dir, got: {item!r}")
        pairs.append((scenario_id, Path(run_dir)))
    return pairs


def main(argv: list[str] | None = None) -> int:
    """Run the deterministic native-convergence helper."""
    args = _build_parser().parse_args(argv)
    try:
        result: dict[str, object] | NativeReportSummary
        if args.command == "initialize":
            result = initialize(
                args.spec,
                args.criteria,
                args.config,
                args.results,
                args.convergence_dir,
                args.actual_model,
            )
        elif args.command == "advance":
            rerun_pairs = _parse_reruns(args.reruns)
            result = advance(args.spec, args.convergence_dir, rerun_pairs)
        else:
            result = report(args.spec, args.convergence_dir, args.output)
        if isinstance(result, NativeReportSummary):
            print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, ValidationError) as exc:
        print(f"{args.command} failed: {_one_line(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
