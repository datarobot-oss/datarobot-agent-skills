# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate behavioral scenario YAML so typos fail in lint, not in a live agent run.

Two layers:
- Structural checks that always run (pyyaml only).
- Full schema validation through the engine's loader when dr_agents_tester is
  importable (the behavioral/e2e environments; skipped in the base
  integration environment).

Plus a packaging guard: scenario/fixture content must never appear under
``skills/`` — everything there ships to end users through every plugin
channel, and the agent under test must not be able to read its own checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BEHAVIORAL_DIR = REPO_ROOT / "tests" / "behavioral"
SKILLS_DIR = REPO_ROOT / "skills"

_REQUIRED_KEYS = {
    "id",
    "kind",
    "name",
    "difficulty",
    "prompt",
    "skills_under_test",
    "success_checks",
}


def _scenario_files() -> list[Path]:
    return sorted(BEHAVIORAL_DIR.glob("journeys/*.yaml")) + sorted(
        BEHAVIORAL_DIR.glob("scenarios/*/*.yaml")
    )


def _scenarios() -> list[tuple[dict[str, Any], Path]]:
    entries: list[tuple[dict[str, Any], Path]] = []
    for path in _scenario_files():
        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict) and "scenarios" in data, (
            f"{path}: expected a top-level 'scenarios' list"
        )
        for item in data["scenarios"]:
            entries.append((item, path))
    return entries


class TestStructure:
    def test_at_least_one_scenario_exists(self) -> None:
        assert _scenario_files(), "tests/behavioral/ has no scenario YAML files"

    def test_required_keys_and_kind(self) -> None:
        for item, path in _scenarios():
            missing = _REQUIRED_KEYS - set(item)
            assert not missing, (
                f"{path}: scenario {item.get('id')!r} missing {sorted(missing)}"
            )
            assert item["kind"] == "behavioral", (
                f"{path}: {item['id']}: kind must be behavioral"
            )

    def test_ids_unique(self) -> None:
        ids = [item["id"] for item, _ in _scenarios()]
        assert len(ids) == len(set(ids)), f"duplicate scenario ids: {ids}"

    def test_skills_under_test_exist(self) -> None:
        for item, path in _scenarios():
            for skill in item["skills_under_test"]:
                skill_dir = SKILLS_DIR / skill
                assert (skill_dir / "SKILL.md").is_file() or any(
                    skill_dir.rglob("SKILL.md")
                ), f"{path}: {item['id']}: unknown skill {skill!r}"

    def test_fixture_sources_exist(self) -> None:
        for item, path in _scenarios():
            for fixture in item.get("fixtures", []):
                source = fixture if isinstance(fixture, str) else fixture["source"]
                resolved = (path.parent / source).resolve()
                assert resolved.is_file(), (
                    f"{path}: {item['id']}: missing fixture {source!r}"
                )

    def test_journeys_are_multi_skill(self) -> None:
        for item, path in _scenarios():
            n_skills = len(item["skills_under_test"])
            if "journeys" in path.parts:
                assert n_skills >= 2, f"{path}: {item['id']}: journeys span 2+ skills"
            else:
                assert n_skills == 1, (
                    f"{path}: {item['id']}: per-skill scenarios test one skill"
                )
                assert path.parent.name == item["skills_under_test"][0], (
                    f"{path}: {item['id']}: directory must match the skill under test"
                )


class TestEngineParse:
    def test_engine_loader_accepts_all_scenarios(self) -> None:
        scenarios_mod = pytest.importorskip(
            "dr_agents_tester.eval.scenarios",
            reason="engine not installed in this environment (behavioral/e2e groups have it)",
        )
        loaded = []
        seen_dirs = sorted({p.parent for p in _scenario_files()})
        for directory in seen_dirs:
            loaded.extend(scenarios_mod.load_behavioral_scenarios(directory))
        assert len(loaded) == len(_scenarios())


class TestPackagingGuard:
    def test_no_scenarios_or_fixtures_ship_inside_skills(self) -> None:
        offenders = [
            p
            for name in ("scenarios", "fixtures")
            for p in SKILLS_DIR.rglob(name)
            if p.is_dir()
        ]
        assert not offenders, (
            f"test content must not live under skills/ (it ships to customers): {offenders}"
        )
