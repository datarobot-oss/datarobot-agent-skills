#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare, run, and aggregate a harness-orchestrated native simulation swarm."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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
from contracts import (
    AgentSpec,
    Scenario,
    ScenarioResult,
    SimulationConfig,
    SwarmPreparation,
    SwarmResults,
    SwarmTask,
)
from native_execution import (
    RESULT_FILENAME,
    STATE_FILENAME,
    NativeRunState,
    initialize,
)

_SCRIPTS_DIR = Path(__file__).parent
_PROMPTS_DIR = _SCRIPTS_DIR.parent / "prompts"

_ROLE_PROMPTS = {
    "runner": "run-scenario.md",
    "fixture": "generate-tool-return.md",
    "evaluator": "evaluate-result.md",
}


def _run_worker(
    role_prompt: Path,
    input_path: Path,
    response_path: Path,
    model: str,
    server_url: str,
    timeout: int,
    rejection_note: str | None = None,
) -> bool:
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "gateway_worker.py"),
        "--role-prompt",
        str(role_prompt),
        "--input-path",
        str(input_path),
        "--response-path",
        str(response_path),
        "--model",
        model,
        "--server-url",
        server_url,
        "--timeout",
        str(timeout),
    ]
    if rejection_note:
        cmd += ["--rejection-note", rejection_note]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
    return result.returncode == 0


def _run_tool_executor(
    input_path: Path,
    response_path: Path,
    tools_path: Path,
    timeout: int,
) -> bool:
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "tool_executor.py"),
        "--input-path",
        str(input_path),
        "--response-path",
        str(response_path),
        "--tools-path",
        str(tools_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"tool_executor timed out after {timeout}s", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
    return result.returncode == 0


def _submit(run_dir: Path, response_path: Path) -> tuple[dict[str, object], str | None]:
    """Call native_execution.py submit. Returns (transition, validation_error_or_None)."""
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS_DIR / "native_execution.py"),
            "submit",
            "--run-dir",
            str(run_dir),
            "--response",
            str(response_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr or ""
        match = re.search(r"role:\S+ validation failed: .+", stderr)
        validation_error = match.group(0) if match else stderr.strip()
        return {}, validation_error
    return json.loads(result.stdout.strip()), None


def _fail(run_dir: Path, reason: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS_DIR / "native_execution.py"),
            "fail",
            "--run-dir",
            str(run_dir),
            "--reason",
            reason,
        ],
        capture_output=True,
        text=True,
    )


def _invoke_role(
    current_role: str,
    current_input: Path,
    current_response: Path,
    model: str,
    server_url: str,
    timeout: int,
    e2e_tools: set[str],
    tools_path: Path | None,
    rejection_note: str | None = None,
) -> bool:
    """Produce one worker response: real executor for selective_e2e readonly
    fixtures, otherwise the gateway worker."""
    if (
        current_role == "fixture"
        and tools_path is not None
        and _fixture_tool_name(current_input) in e2e_tools
    ):
        return _run_tool_executor(current_input, current_response, tools_path, timeout)
    role_prompt = _PROMPTS_DIR / _ROLE_PROMPTS[current_role]
    return _run_worker(
        role_prompt,
        current_input,
        current_response,
        model,
        server_url,
        timeout,
        rejection_note=rejection_note,
    )


def _drive_scenario(
    task: dict[str, object],
    model: str,
    server_url: str,
    timeout: int,
    e2e_tools: set[str],
    tools_path: Path | None,
) -> str:
    """Drive one scenario to completion. Returns final status."""
    run_dir = Path(str(task["run_dir"]))
    current_role = str(task["role"])
    current_input = Path(str(task["input_path"]))
    current_response = Path(str(task["response_path"]))

    def invoke(rejection_note: str | None = None) -> bool:
        return _invoke_role(
            current_role,
            current_input,
            current_response,
            model,
            server_url,
            timeout,
            e2e_tools,
            tools_path,
            rejection_note=rejection_note,
        )

    def fixture_fallback() -> bool:
        return _substitute_fixture_fallback(
            run_dir,
            current_role,
            current_input,
            current_response,
            tools_path,
            e2e_tools,
        )

    while True:
        # Hard worker failure (e.g. the model broke character and emitted prose
        # instead of the JSON envelope): retry once, then fall back for fixtures.
        ok = invoke()
        if not ok:
            ok = invoke("prior attempt did not return the required JSON object")
        if not ok and not fixture_fallback():
            _fail(run_dir, "worker subprocess failed")
            return "error"

        transition, err = _submit(run_dir, current_response)
        if err is not None:
            # Content rejected by validation: retry once, then fall back for fixtures.
            if invoke(err):
                transition, err = _submit(run_dir, current_response)
            if err is not None and fixture_fallback():
                transition, err = _submit(run_dir, current_response)
            if err is not None:
                _fail(run_dir, err)
                return "error"

        next_role = transition.get("role")
        if next_role is None:
            return str(transition.get("status", "error"))

        current_role = str(next_role)
        current_input = Path(str(transition["input_path"]))
        current_response = Path(str(transition["response_path"]))


def _fixture_tool_name(input_path: Path) -> str:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        return str(data.get("tool_name", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def _write_fallback_fixture(input_path: Path, response_path: Path) -> bool:
    """Last-resort fixture when the fixture worker refuses on both attempts.

    Returns a neutral error value for the pending tool call so the scenario can
    still be evaluated instead of erroring out. An error is the least-assumptive
    substitute — it never fabricates a rich success payload the agent under test
    might mishandle — and for "resource unavailable" scenarios it also matches
    what the real tool would return. Callers must surface this as degraded
    coverage; it is not a clean fixture.
    """
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    tool_name = data.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        return False
    fixture = {
        "tool_name": tool_name,
        "args": data.get("args", {}),
        "return_value": {"error": "resource unavailable"},
    }
    try:
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        return False
    return True


def _substitute_fixture_fallback(
    run_dir: Path,
    current_role: str,
    current_input: Path,
    current_response: Path,
    tools_path: Path | None,
    e2e_tools: set[str],
) -> bool:
    """Substitute a synthetic error fixture when the fixture worker is exhausted.

    Scoped to the simulated fixture role only — a failing real (e2e) tool
    execution is a genuine environment signal and is never faked. Surfaces the
    substitution as a `warning:` line so the caller reports degraded coverage.
    """
    if current_role != "fixture":
        return False
    is_e2e_fixture = (
        tools_path is not None and _fixture_tool_name(current_input) in e2e_tools
    )
    if is_e2e_fixture:
        return False
    if not _write_fallback_fixture(current_input, current_response):
        return False
    print(
        f"warning: fixture worker failed for scenario {run_dir.name} "
        f"tool {_fixture_tool_name(current_input)!r}; substituted a synthetic "
        'error return ({"error": "resource unavailable"}). Coverage for this '
        "scenario is degraded — treat its verdict with caution.",
        file=sys.stderr,
    )
    return True


def run(
    spec_path: Path,
    criteria_path: Path,
    config_path: Path,
    runs_dir: Path,
    output_path: Path,
    server_url: str,
    model: str,
    implementation_paths: list[Path] | None,
    tools_path: Path | None,
    max_workers: int,
    timeout: int,
) -> SwarmResults:
    """Prepare, drive all scenarios in parallel, and aggregate results."""
    preparation = prepare(
        spec_path, criteria_path, config_path, runs_dir, implementation_paths
    )

    for warning in preparation.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    spec = load_spec(spec_path.resolve())
    config, _ = load_native_config(
        _resolve_project_file(spec_path.resolve().parent, config_path, "config")
    )
    e2e_tools: set[str] = set()
    if config.execution.mode == "selective_e2e" and tools_path is not None:
        e2e_tools = {t.function_name for t in spec.tools if t.is_readonly}

    tasks = preparation.tasks
    total = len(tasks)
    completed = 0
    t0 = time.monotonic()

    statuses: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for i, task in enumerate(tasks):
            if i > 0:
                time.sleep(0.5)
            futures[
                pool.submit(
                    _drive_scenario,
                    task.model_dump(mode="json"),
                    model,
                    server_url,
                    timeout,
                    e2e_tools,
                    tools_path,
                )
            ] = task
        for future in as_completed(futures):
            task = futures[future]
            completed += 1
            elapsed = time.monotonic() - t0
            try:
                status = future.result()
            except Exception as exc:
                status = "error"
                print(
                    f"scenario {task.scenario_name}: unexpected error: {exc}",
                    file=sys.stderr,
                )
            statuses.append(status)
            symbol = (
                "✓ passed"
                if status == "passed"
                else ("✗ breach" if status in ("breach", "exhausted") else "! error")
            )
            print(
                f"[{completed:3d}/{total}] {symbol:<10} {task.track:<12} {task.scenario_name} ({elapsed:.1f}s)",
                file=sys.stderr,
            )

    elapsed_total = time.monotonic() - t0
    n_passed = statuses.count("passed")
    n_breached = sum(1 for s in statuses if s in ("breach", "exhausted"))
    n_errored = sum(1 for s in statuses if s not in ("passed", "breach", "exhausted"))
    print(
        f"[{total:3d}/{total}] done — {n_passed} passed, {n_breached} breach, {n_errored} error ({elapsed_total:.0f}s)",
        file=sys.stderr,
    )

    return aggregate(spec_path, criteria_path, config_path, runs_dir, output_path)


DEFAULT_IMPLEMENTATION_FILES = ("agent.py", "myagent.py", "tools.py", "app.py")
MAX_IMPLEMENTATION_CHARS = 1_000_000


def prepare(
    spec_path: Path,
    criteria_path: Path,
    config_path: Path,
    runs_dir: Path,
    implementation_paths: list[Path] | None = None,
) -> SwarmPreparation:
    """Validate inputs and initialize one isolated run per confirmed scenario."""
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
    resolved_runs_dir = _resolve_under_root(
        project_root, runs_dir, "swarm runs directory"
    )

    config, warnings = load_native_config(resolved_config)
    spec = load_spec(resolved_spec)
    scenarios = load_criteria(resolved_criteria)
    _validate_confirmed_scenarios(scenarios)

    implementation_files = _resolve_implementation_files(
        project_root, implementation_paths
    )
    warnings.extend(_implementation_warnings(spec, implementation_files))
    _validate_grounding_context(project_root, config)

    for scenario in scenarios:
        run_dir = resolved_runs_dir / _scenario_id(scenario)
        if (run_dir / STATE_FILENAME).exists() or (run_dir / RESULT_FILENAME).exists():
            raise ValueError(f"run already initialized: {run_dir}")

    tasks: list[SwarmTask] = []
    for scenario in scenarios:
        scenario_id = _scenario_id(scenario)
        run_dir = resolved_runs_dir / scenario_id
        transition = initialize(
            resolved_spec,
            resolved_criteria,
            scenario_id,
            run_dir,
            config.evaluation.mode,
            list(config.evaluation.fail_on),
            config.turn_limits.for_track(scenario.track),
        )
        tasks.append(
            SwarmTask.model_validate(
                {
                    "scenario_id": transition["scenario_id"],
                    "scenario_name": scenario.name,
                    "track": scenario.track,
                    "run_dir": transition["run_dir"],
                    "role": transition["role"],
                    "input_path": transition["input_path"],
                    "response_path": transition["response_path"],
                }
            )
        )

    return SwarmPreparation(
        coverage_mode=config.execution.mode,
        tasks=tasks,
        warnings=warnings,
    )


def aggregate(
    spec_path: Path,
    criteria_path: Path,
    config_path: Path,
    runs_dir: Path,
    output_path: Path,
) -> SwarmResults:
    """Validate complete criteria coverage and write ordered aggregate results."""
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
    resolved_runs_dir = _resolve_under_root(
        project_root, runs_dir, "swarm runs directory"
    )
    resolved_output = _resolve_under_root(project_root, output_path, "swarm results")

    config, _ = load_native_config(resolved_config)
    scenarios = load_criteria(resolved_criteria)
    _validate_confirmed_scenarios(scenarios)
    expected_ids = [_scenario_id(scenario) for scenario in scenarios]
    _reject_extra_runs(resolved_runs_dir, set(expected_ids))

    results: list[ScenarioResult] = []
    failures: list[str] = []
    for scenario in scenarios:
        scenario_id = _scenario_id(scenario)
        run_dir = resolved_runs_dir / scenario_id
        result_path = run_dir / RESULT_FILENAME
        state_path = run_dir / STATE_FILENAME
        if result_path.is_file():
            try:
                result = ScenarioResult.model_validate(load_json(result_path))
                if result.scenario.model_dump(mode="json") != scenario.model_dump(
                    mode="json"
                ):
                    raise ValueError("result scenario differs from confirmed criteria")
                results.append(result)
            except (OSError, ValueError, ValidationError) as exc:
                failures.append(f"{scenario_id}: invalid result: {_one_line(exc)}")
        elif state_path.is_file():
            try:
                state = NativeRunState.model_validate(load_json(state_path))
                if state.status == "running":
                    failures.append(
                        f"{scenario_id}: still running; expected role {state.next_role}"
                    )
                else:
                    failures.append(
                        f"{scenario_id}: terminal {state.status} state has no result"
                    )
            except (OSError, ValueError, ValidationError) as exc:
                failures.append(f"{scenario_id}: invalid run state: {_one_line(exc)}")
        else:
            failures.append(f"{scenario_id}: never initialized")

    if failures:
        raise ValueError("; ".join(failures))

    swarm_results = SwarmResults(
        coverage_mode=config.execution.mode,
        scenarios=results,
    )
    write_json(resolved_output, swarm_results.model_dump(mode="json"))
    return swarm_results


def _resolve_implementation_files(
    project_root: Path, implementation_paths: list[Path] | None
) -> list[Path]:
    candidates = (
        implementation_paths
        if implementation_paths
        else [
            project_root / filename
            for filename in DEFAULT_IMPLEMENTATION_FILES
            if (project_root / filename).is_file()
        ]
    )
    if not candidates:
        raise ValueError(
            "no implementation files found; pass --implementation or add "
            "agent.py, myagent.py, tools.py, or app.py"
        )
    return [
        _resolve_project_file(project_root, path, "implementation file")
        for path in candidates
    ]


def _implementation_warnings(
    spec: AgentSpec, implementation_files: list[Path]
) -> list[str]:
    combined = "\n".join(
        path.read_text(encoding="utf-8")[:MAX_IMPLEMENTATION_CHARS]
        for path in implementation_files
    )
    return [
        (
            f"Declared tool {tool.function_name!r} was not discovered in selected "
            "implementation files; simulated coverage can continue."
        )
        for tool in spec.tools
        if not re.search(rf"\b{re.escape(tool.function_name)}\b", combined)
    ]


def _validate_grounding_context(project_root: Path, config: SimulationConfig) -> None:
    context_path = config.grounding.context_path
    if context_path is not None:
        _resolve_project_file(project_root, Path(context_path), "grounding context")


def _validate_confirmed_scenarios(scenarios: list[Scenario]) -> None:
    ids = [_scenario_id(scenario) for scenario in scenarios]
    duplicates = sorted(
        {scenario_id for scenario_id in ids if ids.count(scenario_id) > 1}
    )
    if duplicates:
        raise ValueError(f"duplicate confirmed scenario IDs: {', '.join(duplicates)}")


def _reject_extra_runs(runs_dir: Path, expected_ids: set[str]) -> None:
    if not runs_dir.exists():
        return
    extras = sorted(
        child.name
        for child in runs_dir.iterdir()
        if child.is_dir()
        and child.name not in expected_ids
        and ((child / STATE_FILENAME).exists() or (child / RESULT_FILENAME).exists())
    )
    if extras:
        raise ValueError(f"unexpected scenario run directories: {', '.join(extras)}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("spec", type=Path)
    prepare_parser.add_argument(
        "--criteria", type=Path, default=Path("evaluation_criteria.md")
    )
    prepare_parser.add_argument(
        "--config", type=Path, default=Path("agent_config.yaml")
    )
    prepare_parser.add_argument(
        "--runs-dir", type=Path, default=Path(".datarobot/swarm/runs")
    )
    prepare_parser.add_argument(
        "--implementation", type=Path, action="append", default=None
    )

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("spec", type=Path)
    aggregate_parser.add_argument(
        "--criteria", type=Path, default=Path("evaluation_criteria.md")
    )
    aggregate_parser.add_argument(
        "--config", type=Path, default=Path("agent_config.yaml")
    )
    aggregate_parser.add_argument(
        "--runs-dir", type=Path, default=Path(".datarobot/swarm/runs")
    )
    aggregate_parser.add_argument(
        "--output", type=Path, default=Path(".datarobot/swarm/results.json")
    )

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("spec", type=Path)
    run_parser.add_argument("--server-url", required=True)
    run_parser.add_argument("--model", required=True)
    run_parser.add_argument(
        "--criteria", type=Path, default=Path("evaluation_criteria.md")
    )
    run_parser.add_argument("--config", type=Path, default=Path("agent_config.yaml"))
    run_parser.add_argument(
        "--runs-dir", type=Path, default=Path(".datarobot/swarm/runs")
    )
    run_parser.add_argument(
        "--output", type=Path, default=Path(".datarobot/swarm/results.json")
    )
    run_parser.add_argument(
        "--implementation", type=Path, action="append", default=None
    )
    run_parser.add_argument("--tools-path", type=Path, default=None)
    run_parser.add_argument("--workers", type=int, default=2)
    run_parser.add_argument("--timeout", type=int, default=120)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the deterministic native-swarm helper."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            preparation = prepare(
                args.spec,
                args.criteria,
                args.config,
                args.runs_dir,
                args.implementation,
            )
            payload = preparation.model_dump(mode="json")
        elif args.command == "aggregate":
            swarm_results = aggregate(
                args.spec,
                args.criteria,
                args.config,
                args.runs_dir,
                args.output,
            )
            statuses = [scenario.status for scenario in swarm_results.scenarios]
            payload = {
                "coverage_mode": swarm_results.coverage_mode,
                "total": len(statuses),
                "passed": statuses.count("passed"),
                "breached": statuses.count("breach") + statuses.count("exhausted"),
                "errored": statuses.count("error"),
                "output_path": str(
                    _resolve_under_root(
                        args.spec.resolve().parent, args.output, "swarm results"
                    )
                ),
            }
        else:  # run
            swarm_results = run(
                args.spec,
                args.criteria,
                args.config,
                args.runs_dir,
                args.output,
                args.server_url,
                args.model,
                args.implementation,
                args.tools_path,
                args.workers,
                args.timeout,
            )
            statuses = [scenario.status for scenario in swarm_results.scenarios]
            payload = {
                "coverage_mode": swarm_results.coverage_mode,
                "total": len(statuses),
                "passed": statuses.count("passed"),
                "breached": statuses.count("breach") + statuses.count("exhausted"),
                "errored": statuses.count("error"),
                "output_path": str(
                    _resolve_under_root(
                        args.spec.resolve().parent, args.output, "swarm results"
                    )
                ),
            }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except (OSError, ValueError, ValidationError) as exc:
        print(f"{args.command} failed: {_one_line(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
