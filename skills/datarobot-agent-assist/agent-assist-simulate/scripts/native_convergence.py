#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Initialize and advance harness-native convergence state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from apply_patch import apply_system_prompt_patch, normalize_breach
from artifacts import (
    _one_line,
    _resolve_project_file,
    _resolve_under_root,
    _scenario_id,
    load_criteria,
    load_json,
    load_native_config,
    load_spec,
    update_spec_system_prompt,
    write_json,
)
from contracts import (
    AgentSpec,
    ConvergenceFailure,
    ConvergencePreparation,
    ConvergenceTask,
    FixProposal,
    NativeReportSummary,
    PromptPatchRecord,
    Scenario,
    ScenarioResult,
    SimulationConfig,
    StructuralDiagnosis,
    StrictOutput,
    SwarmResults,
    SwarmTask,
)
from native_execution import RESULT_FILENAME, STATE_FILENAME as RUN_STATE_FILENAME
from native_execution import NativeRunState, initialize as initialize_run
from prompt_inputs import diagnoser_input, fixer_input
from write_report import write_native_report

STATE_FILENAME = "state.json"
ConvergenceStatus = Literal[
    "awaiting_fixers", "rerunning", "awaiting_diagnosers", "complete"
]


class NativeConvergenceState(StrictOutput):
    """Deterministic working state for native convergence."""

    schema_version: Literal[1] = 1
    status: ConvergenceStatus
    spec_path: str
    criteria_path: str
    config_path: str
    initial_results_path: str
    convergence_dir: str
    started_at: str
    completed_at: str | None = None
    initial_spec_hash: str
    expected_spec_hash: str
    initial_system_prompt: str
    current_system_prompt: str
    actual_model: str | None = None
    config: SimulationConfig
    criteria: list[Scenario]
    initial_results: SwarmResults
    latest_results: list[ScenarioResult]
    iteration_counts: dict[str, int]
    patches_applied: list[PromptPatchRecord] = Field(default_factory=list)
    failures: list[ConvergenceFailure] = Field(default_factory=list)
    expected_tasks: list[ConvergenceTask] = Field(default_factory=list)
    rerun_dirs: dict[str, str] = Field(default_factory=dict)


class NativeConvergenceValidationError(ValueError):
    """Raised when a convergence worker response is invalid."""

    def __init__(self, task: ConvergenceTask, reason: str) -> None:
        self.task = task
        self.reason = reason
        super().__init__(f"{task.task_id}: {reason}")


def initialize(
    spec_path: Path,
    criteria_path: Path,
    config_path: Path,
    results_path: Path,
    convergence_dir: Path,
    actual_model: str | None = None,
) -> ConvergencePreparation:
    """Create convergence state and the first fixer or diagnoser task wave."""
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

    raw_spec = resolved_spec.read_text(encoding="utf-8")
    spec = load_spec(resolved_spec)
    if not spec.system_prompt:
        raise ValueError("agent spec is missing system_prompt")
    config, _ = load_native_config(resolved_config)
    criteria = load_criteria(resolved_criteria)
    initial_results = SwarmResults.model_validate(load_json(resolved_results))
    _validate_results_against_criteria(initial_results, criteria)

    latest_results = list(initial_results.scenarios)
    iteration_counts = {_scenario_id(result.scenario): 0 for result in latest_results}
    if config.convergence.max_iterations == 0:
        latest_results = [
            (
                result.model_copy(update={"status": "exhausted"})
                if result.status == "breach"
                else result
            )
            for result in latest_results
        ]

    state = NativeConvergenceState(
        status="complete",
        spec_path=str(resolved_spec),
        criteria_path=str(resolved_criteria),
        config_path=str(resolved_config),
        initial_results_path=str(resolved_results),
        convergence_dir=str(resolved_convergence_dir),
        started_at=datetime.now(timezone.utc).isoformat(),
        initial_spec_hash=_spec_hash(raw_spec),
        expected_spec_hash=_spec_hash(raw_spec),
        initial_system_prompt=spec.system_prompt,
        current_system_prompt=spec.system_prompt,
        actual_model=actual_model,
        config=config,
        criteria=criteria,
        initial_results=initial_results,
        latest_results=latest_results,
        iteration_counts=iteration_counts,
    )
    initial_tasks = _initial_tasks(state, spec)
    state.expected_tasks = initial_tasks
    write_json(state_path, state.model_dump(mode="json"))
    initial_wave: list[ConvergenceTask | SwarmTask] = []
    initial_wave.extend(initial_tasks)
    return ConvergencePreparation(
        status=state.status,
        state_path=str(state_path),
        tasks=initial_wave,
    )


def advance(spec_path: Path, convergence_dir: Path) -> ConvergencePreparation:
    """Validate the current wave and advance convergence atomically."""
    resolved_spec = spec_path.resolve()
    if not resolved_spec.is_file():
        raise ValueError(f"agent spec does not exist: {resolved_spec}")
    project_root = resolved_spec.parent
    resolved_convergence_dir = _resolve_under_root(
        project_root, convergence_dir, "convergence directory"
    )
    state_path = resolved_convergence_dir / STATE_FILENAME
    state = NativeConvergenceState.model_validate(load_json(state_path))
    if Path(state.spec_path) != resolved_spec:
        raise ValueError("convergence state belongs to a different agent spec")
    if Path(state.convergence_dir) != resolved_convergence_dir:
        raise ValueError(
            "convergence state directory does not match requested directory"
        )

    tasks: list[ConvergenceTask | SwarmTask]
    if state.status == "awaiting_fixers":
        tasks = []
        tasks.extend(_apply_fixer_wave(state))
    elif state.status == "rerunning":
        tasks = []
        tasks.extend(_advance_reruns(state))
    elif state.status == "awaiting_diagnosers":
        tasks = []
        tasks.extend(_apply_diagnoser_wave(state))
    elif state.status == "complete":
        tasks = []

    state.expected_tasks = [task for task in tasks if isinstance(task, ConvergenceTask)]
    write_json(state_path, state.model_dump(mode="json"))
    return ConvergencePreparation(
        status=state.status,
        state_path=str(state_path),
        tasks=tasks,
    )


def fail(
    spec_path: Path,
    convergence_dir: Path,
    task_id: str,
    reason: str,
) -> ConvergencePreparation:
    """Record a terminal convergence-worker failure without changing scenario evidence."""
    resolved_spec = spec_path.resolve()
    if not resolved_spec.is_file():
        raise ValueError(f"agent spec does not exist: {resolved_spec}")
    project_root = resolved_spec.parent
    resolved_convergence_dir = _resolve_under_root(
        project_root, convergence_dir, "convergence directory"
    )
    state_path = resolved_convergence_dir / STATE_FILENAME
    state = NativeConvergenceState.model_validate(load_json(state_path))
    if Path(state.spec_path) != resolved_spec:
        raise ValueError("convergence state belongs to a different agent spec")
    if state.status not in {"awaiting_fixers", "awaiting_diagnosers"}:
        raise ValueError(f"convergence is already {state.status}")
    _verify_spec_hash(state)

    matching = [task for task in state.expected_tasks if task.task_id == task_id]
    if not matching:
        raise ValueError(f"task is not currently expected: {task_id}")
    task = matching[0]
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("failure reason must not be empty")

    state.failures.append(
        ConvergenceFailure(
            task_id=task.task_id,
            role=task.role,
            scenario_ids=list(task.scenario_ids),
            reason=normalized_reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    )
    state.expected_tasks = [
        expected
        for expected in state.expected_tasks
        if expected.task_id != task.task_id
    ]
    if not state.expected_tasks:
        next_tasks = _initial_tasks(state, load_spec(Path(state.spec_path)))
        state.expected_tasks = next_tasks

    write_json(state_path, state.model_dump(mode="json"))
    failure_wave: list[ConvergenceTask | SwarmTask] = []
    failure_wave.extend(state.expected_tasks)
    return ConvergencePreparation(
        status=state.status,
        state_path=str(state_path),
        tasks=failure_wave,
    )


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
    if state.expected_tasks or state.rerun_dirs:
        raise ValueError("complete convergence state still has pending work")
    _verify_spec_hash(state)
    return write_native_report(
        state,
        resolved_spec.read_text(encoding="utf-8"),
        resolved_output,
    )


def _initial_tasks(
    state: NativeConvergenceState, spec: AgentSpec
) -> list[ConvergenceTask]:
    blocked_by_role = {
        role: {
            scenario_id
            for failure in state.failures
            if failure.role == role
            for scenario_id in failure.scenario_ids
        }
        for role in ("fixer", "diagnoser")
    }
    breached = [
        result
        for result in state.latest_results
        if result.status == "breach"
        and _scenario_id(result.scenario) not in blocked_by_role["fixer"]
    ]
    exhausted = [
        result
        for result in state.latest_results
        if result.status == "exhausted"
        and result.structural_diagnosis is None
        and _scenario_id(result.scenario) not in blocked_by_role["diagnoser"]
    ]
    convergence_dir = Path(state.convergence_dir)

    if breached:
        state.status = "awaiting_fixers"
        state.completed_at = None
        tasks: list[ConvergenceTask] = []
        for cluster in _cluster_breaches(breached):
            task_id = _fixer_task_id(cluster)
            task_dir = convergence_dir / "fixers" / task_id
            input_path = task_dir / "input.json"
            response_path = task_dir / "output.json"
            write_json(
                input_path,
                fixer_input(cluster, spec.system_prompt or "", state.patches_applied),
            )
            tasks.append(
                ConvergenceTask(
                    task_id=task_id,
                    role="fixer",
                    scenario_ids=[_scenario_id(result.scenario) for result in cluster],
                    input_path=str(input_path),
                    response_path=str(response_path),
                )
            )
        return tasks

    if exhausted:
        state.status = "awaiting_diagnosers"
        state.completed_at = None
        tasks = []
        for result in exhausted:
            scenario_id = _scenario_id(result.scenario)
            task_id = f"diag_{scenario_id.removeprefix('scn_')}"
            task_dir = convergence_dir / "diagnosers" / scenario_id
            input_path = task_dir / "input.json"
            response_path = task_dir / "output.json"
            write_json(
                input_path,
                diagnoser_input(
                    result, state.patches_applied, state.current_system_prompt
                ),
            )
            tasks.append(
                ConvergenceTask(
                    task_id=task_id,
                    role="diagnoser",
                    scenario_ids=[scenario_id],
                    input_path=str(input_path),
                    response_path=str(response_path),
                )
            )
        return tasks

    state.status = "complete"
    if state.completed_at is None:
        state.completed_at = datetime.now(timezone.utc).isoformat()
    return []


def _apply_diagnoser_wave(
    state: NativeConvergenceState,
) -> list[ConvergenceTask]:
    _verify_spec_hash(state)
    diagnoser_tasks = [
        task for task in state.expected_tasks if task.role == "diagnoser"
    ]
    if not diagnoser_tasks or len(diagnoser_tasks) != len(state.expected_tasks):
        raise ValueError("awaiting_diagnosers state has invalid expected tasks")

    result_by_id = {
        _scenario_id(result.scenario): result for result in state.latest_results
    }
    validated: dict[str, StructuralDiagnosis] = {}
    for task in diagnoser_tasks:
        try:
            if len(task.scenario_ids) != 1:
                raise ValueError("diagnoser task must address exactly one scenario")
            scenario_id = task.scenario_ids[0]
            result = result_by_id.get(scenario_id)
            if result is None or result.status != "exhausted":
                raise ValueError(
                    "diagnoser task does not reference an exhausted scenario"
                )
            if result.structural_diagnosis is not None:
                raise ValueError(
                    "exhausted scenario already has a structural diagnosis"
                )
            validated[scenario_id] = StructuralDiagnosis.model_validate(
                load_json(Path(task.response_path))
            )
        except (OSError, ValueError, ValidationError) as exc:
            raise NativeConvergenceValidationError(task, _one_line(exc)) from exc

    state.latest_results = [
        (
            result.model_copy(
                update={
                    "structural_diagnosis": validated[_scenario_id(result.scenario)]
                }
            )
            if _scenario_id(result.scenario) in validated
            else result
        )
        for result in state.latest_results
    ]
    return _initial_tasks(state, load_spec(Path(state.spec_path)))


def _apply_fixer_wave(
    state: NativeConvergenceState,
) -> list[SwarmTask]:
    _verify_spec_hash(state)
    fixer_tasks = [task for task in state.expected_tasks if task.role == "fixer"]
    if not fixer_tasks or len(fixer_tasks) != len(state.expected_tasks):
        raise ValueError("awaiting_fixers state has invalid expected tasks")

    validated: list[tuple[ConvergenceTask, FixProposal]] = []
    proposed_patches: set[str] = set()
    existing_patches = {
        patch.system_prompt_patch.strip() for patch in state.patches_applied
    }
    for task in fixer_tasks:
        try:
            proposal = FixProposal.model_validate(load_json(Path(task.response_path)))
            if proposal.addresses_scenarios != task.scenario_ids:
                raise ValueError(
                    "addresses_scenarios must exactly match the active cluster"
                )
            patch = proposal.system_prompt_patch.strip()
            if not patch:
                raise ValueError("system_prompt_patch must not be empty")
            if patch in existing_patches or patch in proposed_patches:
                raise ValueError("system_prompt_patch duplicates an existing proposal")
            proposed_patches.add(patch)
            validated.append((task, proposal))
        except (OSError, ValueError, ValidationError) as exc:
            raise NativeConvergenceValidationError(task, _one_line(exc)) from exc

    rerun_plan: list[tuple[str, Path, ScenarioResult]] = []
    result_by_id = {
        _scenario_id(result.scenario): result for result in state.latest_results
    }
    for task, _ in validated:
        for scenario_id in task.scenario_ids:
            iteration = state.iteration_counts[scenario_id] + 1
            run_dir = (
                Path(state.convergence_dir)
                / "runs"
                / scenario_id
                / f"iteration-{iteration}"
            )
            if (run_dir / RUN_STATE_FILENAME).exists() or (
                run_dir / RESULT_FILENAME
            ).exists():
                raise ValueError(f"rerun already initialized: {run_dir}")
            rerun_plan.append((scenario_id, run_dir, result_by_id[scenario_id]))

    raw_spec = Path(state.spec_path).read_text(encoding="utf-8")
    current_prompt = state.current_system_prompt
    patch_records: list[PromptPatchRecord] = []
    for task, proposal in validated:
        prompt_before = current_prompt
        current_prompt = apply_system_prompt_patch(
            current_prompt, proposal.system_prompt_patch.strip()
        )
        next_iterations = [
            state.iteration_counts[scenario_id] + 1 for scenario_id in task.scenario_ids
        ]
        patch_records.append(
            PromptPatchRecord(
                cluster_id=task.task_id,
                iteration=max(next_iterations),
                timestamp=datetime.now(timezone.utc).isoformat(),
                description=proposal.description,
                system_prompt_patch=proposal.system_prompt_patch.strip(),
                reasoning=proposal.reasoning,
                addresses_scenarios=list(task.scenario_ids),
                prompt_hash_before=_spec_hash(prompt_before),
                prompt_hash_after=_spec_hash(current_prompt),
            )
        )

    update_spec_system_prompt(Path(state.spec_path), raw_spec, current_prompt)
    updated_spec_text = Path(state.spec_path).read_text(encoding="utf-8")
    state.current_system_prompt = current_prompt
    state.expected_spec_hash = _spec_hash(updated_spec_text)
    state.patches_applied.extend(patch_records)

    tasks: list[SwarmTask] = []
    state.rerun_dirs = {}
    for scenario_id, run_dir, prior_result in rerun_plan:
        state.iteration_counts[scenario_id] += 1
        scenario = prior_result.scenario
        transition = initialize_run(
            Path(state.spec_path),
            Path(state.criteria_path),
            scenario_id,
            run_dir,
            state.config.evaluation.mode,
            list(state.config.evaluation.fail_on),
            state.config.turn_limits.for_track(scenario.track),
            list(prior_result.fixture_history),
        )
        tasks.append(
            SwarmTask.model_validate(
                {
                    "scenario_id": transition["scenario_id"],
                    "scenario_name": transition["scenario_name"],
                    "track": scenario.track,
                    "run_dir": transition["run_dir"],
                    "role": transition["role"],
                    "input_path": transition["input_path"],
                    "response_path": transition["response_path"],
                }
            )
        )
        state.rerun_dirs[scenario_id] = str(run_dir)

    state.status = "rerunning"
    return tasks


def _advance_reruns(
    state: NativeConvergenceState,
) -> list[ConvergenceTask]:
    _verify_spec_hash(state)
    if not state.rerun_dirs:
        raise ValueError("rerunning state has no expected rerun directories")

    rerun_results: dict[str, ScenarioResult] = {}
    failures: list[str] = []
    current_by_id = {
        _scenario_id(result.scenario): result for result in state.latest_results
    }
    for scenario_id, run_dir_text in state.rerun_dirs.items():
        run_dir = Path(run_dir_text)
        result_path = run_dir / RESULT_FILENAME
        run_state_path = run_dir / RUN_STATE_FILENAME
        if result_path.is_file():
            try:
                result = ScenarioResult.model_validate(load_json(result_path))
                if result.scenario.model_dump(mode="json") != current_by_id[
                    scenario_id
                ].scenario.model_dump(mode="json"):
                    raise ValueError("rerun scenario differs from confirmed criteria")
                rerun_results[scenario_id] = result
            except (OSError, ValueError, ValidationError) as exc:
                failures.append(
                    f"{scenario_id}: invalid rerun result: {_one_line(exc)}"
                )
        elif run_state_path.is_file():
            try:
                run_state = NativeRunState.model_validate(load_json(run_state_path))
                if run_state.status == "running":
                    failures.append(
                        f"{scenario_id}: rerun still running; "
                        f"expected role {run_state.next_role}"
                    )
                else:
                    failures.append(
                        f"{scenario_id}: terminal rerun state has no result"
                    )
            except (OSError, ValueError, ValidationError) as exc:
                failures.append(f"{scenario_id}: invalid rerun state: {_one_line(exc)}")
        else:
            failures.append(f"{scenario_id}: rerun was never initialized")

    if failures:
        raise ValueError("; ".join(failures))

    latest: list[ScenarioResult] = []
    max_iterations = state.config.convergence.max_iterations
    for result in state.latest_results:
        scenario_id = _scenario_id(result.scenario)
        replacement = rerun_results.get(scenario_id, result)
        if (
            replacement.status == "breach"
            and state.iteration_counts[scenario_id] >= max_iterations
        ):
            replacement = replacement.model_copy(update={"status": "exhausted"})
        latest.append(replacement)
    state.latest_results = latest
    state.rerun_dirs = {}
    return _initial_tasks(state, load_spec(Path(state.spec_path)))


def _verify_spec_hash(state: NativeConvergenceState) -> None:
    current_hash = _spec_hash(Path(state.spec_path).read_text(encoding="utf-8"))
    if current_hash != state.expected_spec_hash:
        raise ValueError(
            "agent spec changed outside convergence; refusing to overwrite it"
        )


def _cluster_breaches(
    breached: list[ScenarioResult],
) -> list[list[ScenarioResult]]:
    clusters: dict[tuple[str, str, str], list[ScenarioResult]] = {}
    for result in breached:
        scenario_id = _scenario_id(result.scenario)
        normalized_reason = normalize_breach(
            result.breach_reason or result.evaluation_reason or ""
        )
        key = (
            result.scenario.track,
            result.scenario.capability_targeted or "",
            normalized_reason or scenario_id,
        )
        clusters.setdefault(key, []).append(result)
    return list(clusters.values())


def _fixer_task_id(cluster: list[ScenarioResult]) -> str:
    payload = [
        {
            "scenario_id": _scenario_id(result.scenario),
            "track": result.scenario.track,
            "capability": result.scenario.capability_targeted,
            "reason": normalize_breach(
                result.breach_reason or result.evaluation_reason or ""
            ),
        }
        for result in cluster
    ]
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return f"fix_{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"


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


def _spec_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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

    fail_parser = subparsers.add_parser("fail")
    fail_parser.add_argument("spec", type=Path)
    fail_parser.add_argument(
        "--convergence-dir",
        type=Path,
        default=Path(".datarobot/swarm/convergence"),
    )
    fail_parser.add_argument("--task-id", required=True)
    fail_parser.add_argument("--reason", required=True)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("spec", type=Path)
    report_parser.add_argument(
        "--convergence-dir",
        type=Path,
        default=Path(".datarobot/swarm/convergence"),
    )
    report_parser.add_argument("--output", type=Path, default=Path("eval_report.md"))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the deterministic native-convergence helper."""
    args = _build_parser().parse_args(argv)
    try:
        result: ConvergencePreparation | NativeReportSummary
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
            result = advance(args.spec, args.convergence_dir)
        elif args.command == "fail":
            result = fail(
                args.spec,
                args.convergence_dir,
                args.task_id,
                args.reason,
            )
        else:
            result = report(args.spec, args.convergence_dir, args.output)
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
        return 0
    except NativeConvergenceValidationError as exc:
        print(
            f"task:{exc.task.task_id} role:{exc.task.role} "
            f"validation failed: {exc.reason}",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, ValidationError) as exc:
        print(f"{args.command} failed: {_one_line(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
