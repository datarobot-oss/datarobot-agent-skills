#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare, validate, and confirm harness-native scenario generation."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from artifacts import (
    load_json,
    load_spec,
    read_generated_code,
    save_config,
    write_criteria,
    write_json,
)
from contracts import (
    Scenario,
    ScenarioProposal,
    ScenarioProposalList,
    confirm_scenario,
)
from prompt_inputs import attack_input, behavior_input, persistence_input

Role = Literal["attack", "behavior", "persistence"]
ROLES: tuple[Role, ...] = ("attack", "behavior", "persistence")


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
    spec = load_spec(spec_path)
    grounding_context = (
        grounding_context_path.read_text(encoding="utf-8")
        if grounding_context_path
        else None
    )
    implementation_context = read_generated_code(spec_path.parent)
    packages: dict[Role, dict[str, object]] = {
        "attack": attack_input(spec),
        "behavior": behavior_input(spec, user_persona, grounding_context),
        "persistence": persistence_input(spec, implementation_context),
    }

    paths: dict[Role, Path] = {}
    for role, package in packages.items():
        path = work_dir / f"{role}-input.json"
        write_json(path, package)
        paths[role] = path
    return paths


def validate_role_output(role: Role, data: object) -> list[ScenarioProposal]:
    """Validate one generator response and enforce its assigned track."""
    proposals = ScenarioProposalList.model_validate(data).scenarios
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


def _one_line(exc: Exception) -> str:
    return re.sub(r"\s+", " ", str(exc)).strip()


def _print_candidates(candidates: ScenarioProposalList) -> None:
    for role in ROLES:
        role_scenarios = [
            scenario for scenario in candidates.scenarios if scenario.track == role
        ]
        print(f"{role.upper()} ({len(role_scenarios)}):")
        for scenario in role_scenarios:
            print(f"- {scenario.name}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("spec", type=Path)
    prepare_parser.add_argument("--user-persona", required=True)
    prepare_parser.add_argument("--context", type=Path)
    prepare_parser.add_argument("--iterations", type=int, default=3)
    prepare_parser.add_argument(
        "--judge-mode", choices=["standard", "scored"], default="standard"
    )
    prepare_parser.add_argument("--model", default="anthropic/claude-sonnet-4-6")
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
        if args.command == "prepare":
            paths = prepare(args.spec, args.user_persona, args.context, args.work_dir)
            save_config(args.user_persona, args.iterations, args.judge_mode, args.model)
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
