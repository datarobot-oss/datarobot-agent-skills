#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare, validate, and confirm harness-native scenario generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from artifacts import (
    _one_line,
    _resolve_project_file,
    _resolve_under_root,
    load_json,
    load_native_config,
    load_spec,
    read_generated_code,
    save_native_config,
    write_criteria,
    write_json,
)
from contracts import (
    ConvergenceConfig,
    EvaluationConfig,
    ExecutionConfig,
    GroundingConfig,
    PersonaConfig,
    Scenario,
    ScenarioProposal,
    ScenarioProposalList,
    SimulationConfig,
    confirm_scenario,
)
from prompt_inputs import attack_input, behavior_input, persistence_input

Role = Literal["attack", "behavior", "persistence"]
ROLES: tuple[Role, ...] = ("attack", "behavior", "persistence")
ROLE_SCENARIO_LIMITS: dict[Role, int] = {
    "attack": 6,
    "behavior": 3,
    "persistence": 3,
}


class NativeScenarioValidationError(ValueError):
    """Raised when one or more native generator responses are invalid."""

    def __init__(self, failures: dict[Role, str]) -> None:
        self.failures = failures
        super().__init__(
            "; ".join(f"{role}: {reason}" for role, reason in failures.items())
        )


def prepare(
    spec_path: Path,
    user_persona: str,
    grounding_context_path: Path | None,
    work_dir: Path,
) -> dict[Role, Path]:
    """Write minimal input packages for the three scenario generators."""
    resolved_spec = spec_path.resolve()
    project_root = resolved_spec.parent
    resolved_work_dir = _resolve_under_root(project_root, work_dir, "work directory")
    resolved_context = (
        _resolve_project_file(project_root, grounding_context_path, "grounding context")
        if grounding_context_path
        else None
    )
    spec = load_spec(resolved_spec)
    grounding_context = (
        resolved_context.read_text(encoding="utf-8") if resolved_context else None
    )
    implementation_context = read_generated_code(project_root)
    packages: dict[Role, dict[str, object]] = {
        "attack": attack_input(spec),
        "behavior": behavior_input(spec, user_persona, grounding_context),
        "persistence": persistence_input(spec, implementation_context),
    }

    paths: dict[Role, Path] = {}
    for role, package in packages.items():
        path = resolved_work_dir / f"{role}-input.json"
        write_json(path, package)
        paths[role] = path
    return paths


def configure(
    spec_path: Path,
    user_persona: str,
    grounding_context_path: Path | None,
    iterations: int,
    judge_mode: Literal["standard", "scored"],
    output_path: Path,
    model: str | None = None,
    execution_mode: str = "simulated",
) -> Path:
    """Persist the public native configuration collected by the harness."""
    project_root = spec_path.resolve().parent
    resolved_output = _resolve_under_root(
        project_root, output_path, "simulation config"
    )
    context_path = (
        str(
            _resolve_project_file(
                project_root, grounding_context_path, "grounding context"
            ).relative_to(project_root)
        )
        if grounding_context_path
        else None
    )
    save_native_config(
        SimulationConfig(
            persona=PersonaConfig(description=user_persona),
            grounding=GroundingConfig(context_path=context_path),
            evaluation=EvaluationConfig(mode=judge_mode),
            convergence=ConvergenceConfig(max_iterations=iterations),
            execution=ExecutionConfig(mode=execution_mode),
            model=model,
        ),
        resolved_output,
    )
    return resolved_output


def prepare_from_config(
    spec_path: Path,
    config_path: Path,
    work_dir: Path,
) -> dict[Role, Path]:
    """Load native configuration and prepare the three generator packages."""
    project_root = spec_path.resolve().parent
    resolved_config = _resolve_project_file(
        project_root, config_path, "simulation config"
    )
    config, warnings = load_native_config(resolved_config)
    for warning in warnings:
        print(f"warning:{warning}", file=sys.stderr)
    context_path = (
        Path(config.grounding.context_path)
        if config.grounding.context_path is not None
        else None
    )
    return prepare(
        spec_path,
        config.persona.description,
        context_path,
        work_dir,
    )


def validate_role_output(role: Role, data: object) -> list[ScenarioProposal]:
    """Validate one generator response and enforce its assigned track."""
    proposals = ScenarioProposalList.model_validate(data).scenarios
    limit = ROLE_SCENARIO_LIMITS[role]
    if len(proposals) > limit:
        raise ValueError(
            f"{role} generator returned {len(proposals)} scenarios; maximum is {limit}"
        )
    wrong_tracks = sorted(
        {proposal.track for proposal in proposals if proposal.track != role}
    )
    if wrong_tracks:
        raise ValueError(
            f"expected only {role} scenarios, received tracks: {', '.join(wrong_tracks)}"
        )
    return proposals


def finalize(work_dir: Path) -> ScenarioProposalList:
    """Validate all generator responses and persist review candidates."""
    failures: dict[Role, str] = {}
    combined: list[ScenarioProposal] = []

    for role in ROLES:
        try:
            data = load_json(work_dir / f"{role}-output.json")
            combined.extend(validate_role_output(role, data))
        except (OSError, ValueError, ValidationError) as exc:
            failures[role] = _one_line(exc)

    if failures:
        raise NativeScenarioValidationError(failures)

    candidates = ScenarioProposalList(scenarios=combined)
    write_json(work_dir / "candidates.json", candidates.model_dump(mode="json"))
    return candidates


def confirm(work_dir: Path, output_path: Path) -> list[Scenario]:
    """Validate reviewed candidates, assign stable IDs, and write public criteria."""
    candidates = ScenarioProposalList.model_validate(
        load_json(work_dir / "candidates.json")
    )
    scenarios = [confirm_scenario(proposal) for proposal in candidates.scenarios]
    _require_unique_scenarios(scenarios)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_criteria(scenarios, output_path)
    return scenarios


def _require_unique_scenarios(scenarios: list[Scenario]) -> None:
    names = [scenario.name for scenario in scenarios]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        raise ValueError(f"duplicate scenario names: {', '.join(duplicate_names)}")

    ids = [scenario.scenario_id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario content")


def _print_candidates(candidates: ScenarioProposalList) -> None:
    for role in ROLES:
        role_scenarios = [
            scenario for scenario in candidates.scenarios if scenario.track == role
        ]
        print(f"{role.upper()} ({len(role_scenarios)}):")
        for scenario in role_scenarios:
            print(f"- {scenario.name}")
            print(f"  Capability: {scenario.capability_targeted or 'N/A'}")
            print(f"  Max turns: {scenario.max_turns}")
            print("  Turns:")
            for turn in scenario.turns:
                print(f"    - {turn}")
            print(f"  Expected safe behavior: {scenario.expected_safe_behavior}")
            print("  Breach indicators:")
            for indicator in scenario.breach_indicators:
                print(f"    - {indicator}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure_parser = subparsers.add_parser("configure")
    configure_parser.add_argument("spec", type=Path)
    configure_parser.add_argument("--user-persona", required=True)
    configure_parser.add_argument("--context", type=Path)
    configure_parser.add_argument("--iterations", type=int, default=3)
    configure_parser.add_argument(
        "--judge-mode", choices=["standard", "scored"], default="standard"
    )
    configure_parser.add_argument("--model", default=None)
    configure_parser.add_argument(
        "--execution-mode",
        choices=["simulated", "selective_e2e"],
        default="simulated",
    )
    configure_parser.add_argument(
        "--output", type=Path, default=Path("agent_config.yaml")
    )

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("spec", type=Path)
    prepare_parser.add_argument(
        "--config", type=Path, default=Path("agent_config.yaml")
    )
    prepare_parser.add_argument(
        "--work-dir", type=Path, default=Path(".datarobot/swarm")
    )

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument(
        "--work-dir", type=Path, default=Path(".datarobot/swarm")
    )

    confirm_parser = subparsers.add_parser("confirm")
    confirm_parser.add_argument(
        "--work-dir", type=Path, default=Path(".datarobot/swarm")
    )
    confirm_parser.add_argument(
        "--output", type=Path, default=Path("evaluation_criteria.md")
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the internal native-scenario helper."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "configure":
            config_path = configure(
                args.spec,
                args.user_persona,
                args.context,
                args.iterations,
                args.judge_mode,
                args.output,
                args.model,
                args.execution_mode,
            )
            print(f"config:{config_path}")
        elif args.command == "prepare":
            paths = prepare_from_config(args.spec, args.config, args.work_dir)
            for role in ROLES:
                print(f"{role}:{paths[role]}")
        elif args.command == "finalize":
            _print_candidates(finalize(args.work_dir))
        else:
            scenarios = confirm(args.work_dir, args.output)
            print(f"Confirmed {len(scenarios)} scenarios in {args.output}")
        return 0
    except NativeScenarioValidationError as exc:
        for role, reason in exc.failures.items():
            print(f"role:{role} validation failed: {reason}", file=sys.stderr)
        return 1
    except (OSError, ValueError, ValidationError) as exc:
        print(f"{args.command} failed: {_one_line(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
