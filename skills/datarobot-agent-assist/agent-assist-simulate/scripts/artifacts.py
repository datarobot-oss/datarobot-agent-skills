#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic spec, criteria, and configuration artifact helpers."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

from swarm_contracts import AgentSpec, Scenario, SimulationConfig


class CriteriaError(ValueError):
    """Raised when confirmed evaluation criteria cannot be loaded safely."""


class ConfigError(ValueError):
    """Raised when simulation configuration cannot be loaded safely."""


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
    priority = ["tools.py", "agent.py", "myagent.py", "app.py"]
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


def load_native_config(path: Path) -> tuple[SimulationConfig, list[str]]:
    """Load native configuration, migrating legacy Gateway fields in memory."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} contains invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a configuration mapping")
    try:
        if data.get("schema_version") == 1:
            return SimulationConfig.model_validate(data), []
        if "user_type" not in data:
            raise ConfigError(
                f"{path} is neither schema_version 1 nor a recognized legacy config"
            )
        migrated = SimulationConfig.model_validate(
            {
                "schema_version": 1,
                "persona": {"description": data["user_type"]},
                "grounding": {"context_path": None},
                "evaluation": {
                    "mode": data.get("judge_mode", "standard"),
                    "fail_on": ["high", "critical"],
                },
                "convergence": {
                    "max_iterations": data.get("max_convergence_iterations", 3)
                },
                "turn_limits": {"attack": 6, "behavior": 3, "persistence": 6},
                "execution": {
                    "mode": "simulated",
                    "requested_scope": {"tools": [], "resources": []},
                },
            }
        )
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(f"{path} contains invalid configuration: {exc}") from exc

    warnings = ["Migrated legacy Gateway configuration in memory for native execution."]
    if data.get("llm_judge_model"):
        warnings.append(
            "Ignored legacy llm_judge_model; native execution uses the active harness model."
        )
    return migrated, warnings


def save_native_config(config: SimulationConfig, path: Path) -> None:
    """Persist the versioned native simulation configuration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            config.model_dump(mode="json"),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def _one_line(exc: Exception) -> str:
    return re.sub(r"\s+", " ", str(exc)).strip()


def _scenario_id(scenario: Scenario) -> str:
    if not scenario.scenario_id:
        raise ValueError(f"confirmed scenario is missing scenario_id: {scenario.name}")
    return scenario.scenario_id


def _resolve_under_root(project_root: Path, path: Path, label: str) -> Path:
    candidate = path if path.is_absolute() else project_root / path
    resolved = candidate.resolve()
    if not resolved.is_relative_to(project_root):
        raise ValueError(f"{label} escapes project root: {path}")
    return resolved


def _resolve_project_file(project_root: Path, path: Path, label: str) -> Path:
    resolved = _resolve_under_root(project_root, path, label)
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {resolved}")
    return resolved
