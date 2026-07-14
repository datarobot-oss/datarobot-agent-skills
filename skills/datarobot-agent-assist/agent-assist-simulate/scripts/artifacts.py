#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic spec, criteria, and configuration artifact helpers."""

import json
from pathlib import Path
from typing import Any

import yaml

from contracts import AgentSpec, Scenario


class CriteriaError(ValueError):
    """Raised when confirmed evaluation criteria cannot be loaded safely."""


def write_json(path: Path, data: object) -> None:
    """Write an internal JSON artifact, creating its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_json(path: Path) -> Any:
    """Load an internal JSON artifact."""
    with path.open(encoding="utf-8") as artifact_file:
        return json.load(artifact_file)


def read_generated_code(directory: Path | None = None) -> str | None:
    """Read a bounded implementation-code summary for scenario generation."""
    priority = ["tools.py", "agent.py", "app.py"]
    candidates: list[Path] = []
    root = directory or Path.cwd()
    for name in priority:
        path = root / name
        if path.is_file():
            candidates.append(path)
    if not candidates:
        return None

    parts: list[str] = []
    for path in candidates[:3]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[:200]
            parts.append(f"# File: {path.name}\n" + "\n".join(lines) + "\n")
        except OSError:
            continue
    return "\n".join(parts) if parts else None


def load_spec(path: Path) -> AgentSpec:
    """Load and validate an agent specification."""
    with path.open(encoding="utf-8") as spec_file:
        data = yaml.safe_load(spec_file)
    return AgentSpec.model_validate(data)


def write_criteria(scenarios: list[Scenario], path: Path) -> None:
    """Persist generated or confirmed evaluation criteria."""
    data = [scenario.model_dump() for scenario in scenarios]
    path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8"
    )


def load_criteria(path: Path) -> list[Scenario]:
    """Load a non-empty, validated confirmed scenario list."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CriteriaError(f"could not read {path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CriteriaError(f"{path} contains invalid YAML: {exc}") from exc

    if not isinstance(data, list) or not data:
        raise CriteriaError(f"{path} must contain a non-empty list of scenarios")

    try:
        return [Scenario.model_validate(scenario) for scenario in data]
    except Exception as exc:
        raise CriteriaError(f"{path} contains an invalid scenario: {exc}") from exc


def save_config(
    user_type: str,
    iterations: int,
    judge_mode: str,
    model: str,
    path: Path | None = None,
) -> None:
    """Persist the current Gateway-compatible simulation configuration."""
    config = {
        "user_type": user_type,
        "max_convergence_iterations": iterations,
        "judge_mode": judge_mode,
        "llm_judge_model": model,
    }
    destination = path or Path("agent_config.yaml")
    destination.write_text(
        yaml.dump(config, default_flow_style=False), encoding="utf-8"
    )


def update_spec_system_prompt(
    path: Path, raw_spec_text: str, system_prompt: str
) -> None:
    """Persist a hardened system prompt without changing other spec fields."""
    updated = yaml.safe_load(raw_spec_text)
    updated["system_prompt"] = system_prompt
    path.write_text(
        yaml.dump(
            updated, default_flow_style=False, sort_keys=False, allow_unicode=True
        ),
        encoding="utf-8",
    )
