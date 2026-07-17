# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Literal

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT_DIR = (
    REPO_ROOT
    / "skills"
    / "datarobot-agent-assist"
    / "agent-assist-simulate"
    / "scripts"
)
SCRIPT_PATH = SCRIPT_DIR / "native_scenarios.py"
SKILL_PATH = SCRIPT_DIR.parent / "SKILL.md"
sys.path.insert(0, str(SCRIPT_DIR))
artifacts = importlib.import_module("artifacts")
contracts = importlib.import_module("contracts")
native = importlib.import_module("native_scenarios")


def proposal_data(track: str, name: str) -> dict[str, object]:
    return {
        "name": name,
        "track": track,
        "capability_targeted": "fetch_records" if track != "behavior" else None,
        "turns": [f"{name} user turn"],
        "expected_safe_behavior": f"{name} expected behavior",
        "breach_indicators": [f"{name} breach"],
        "max_turns": 6 if track != "behavior" else 3,
    }


def write_role_outputs(work_dir: Path) -> None:
    for role in native.ROLES:
        artifacts.write_json(
            work_dir / f"{role}-output.json",
            {"scenarios": [proposal_data(role, f"{role} scenario")]},
        )


def write_spec(tmp_path: Path) -> Path:
    spec_path = tmp_path / "agent_spec.md"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "system_prompt": "Only return records in the user's scope.",
                "tools": [
                    {
                        "function_name": "fetch_records",
                        "inputs": [{"arg_name": "limit", "type": "int"}],
                        "out": [{"arg_name": "records", "type": "list"}],
                    }
                ],
                "examples": ["Summarize my open records."],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        "def fetch_records(limit: int):\n    return []\n", encoding="utf-8"
    )
    return spec_path


def test_prepare_writes_isolated_role_inputs(tmp_path: Path) -> None:
    spec_path = write_spec(tmp_path)
    context_path = tmp_path / "user_context.txt"
    context_path.write_text("Users often omit time ranges.", encoding="utf-8")
    work_dir = tmp_path / ".datarobot" / "swarm"

    native.prepare(spec_path, "support analysts", context_path, work_dir)

    attack = artifacts.load_json(work_dir / "attack-input.json")
    behavior = artifacts.load_json(work_dir / "behavior-input.json")
    persistence = artifacts.load_json(work_dir / "persistence-input.json")
    assert set(attack) == {"system_prompt", "tools"}
    assert set(behavior) == {
        "system_prompt",
        "user_persona",
        "examples",
        "grounding_context",
    }
    assert set(persistence) == {
        "system_prompt",
        "tools",
        "implementation_context",
    }
    assert behavior["user_persona"] == "support analysts"
    assert "fetch_records" in persistence["implementation_context"]


def test_prepare_cli_persists_native_config_with_grounding_path(
    tmp_path: Path,
) -> None:
    spec_path = write_spec(tmp_path)
    work_dir = tmp_path / ".datarobot" / "swarm"
    context_path = tmp_path / "user_context.txt"
    context_path.write_text("Users often omit time ranges.", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "configure",
            str(spec_path),
            "--user-persona",
            "support analysts",
            "--iterations",
            "4",
            "--judge-mode",
            "scored",
            "--context",
            str(context_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    config, warnings = artifacts.load_native_config(tmp_path / "agent_config.yaml")
    assert warnings == []
    assert config.schema_version == 1
    assert config.persona.description == "support analysts"
    assert config.grounding.context_path == "user_context.txt"
    assert config.convergence.max_iterations == 4
    assert config.evaluation.mode == "scored"

    prepared = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "prepare",
            str(spec_path),
            "--work-dir",
            str(work_dir),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert prepared.returncode == 0
    assert (work_dir / "behavior-input.json").is_file()


def test_prepare_rejects_context_and_work_directory_path_escape(
    tmp_path: Path,
) -> None:
    spec_path = write_spec(tmp_path)
    outside_context = tmp_path.parent / "outside-context.txt"
    outside_context.write_text("sensitive", encoding="utf-8")

    with pytest.raises(ValueError, match="grounding context escapes project root"):
        native.prepare(
            spec_path,
            "support analysts",
            outside_context,
            tmp_path / ".datarobot" / "swarm",
        )

    with pytest.raises(ValueError, match="work directory escapes project root"):
        native.prepare(
            spec_path,
            "support analysts",
            None,
            tmp_path.parent / "outside-work",
        )


def test_finalize_validates_and_writes_candidates(tmp_path: Path) -> None:
    work_dir = tmp_path / ".datarobot" / "swarm"
    write_role_outputs(work_dir)

    candidates = native.finalize(work_dir)

    assert [scenario.track for scenario in candidates.scenarios] == [
        "attack",
        "behavior",
        "persistence",
    ]
    persisted = contracts.ScenarioProposalList.model_validate(
        artifacts.load_json(work_dir / "candidates.json")
    )
    assert len(persisted.scenarios) == 3


def test_finalize_rejects_entire_wrong_track_response(tmp_path: Path) -> None:
    work_dir = tmp_path / ".datarobot" / "swarm"
    write_role_outputs(work_dir)
    artifacts.write_json(
        work_dir / "attack-output.json",
        {
            "scenarios": [
                proposal_data("attack", "valid attack"),
                proposal_data("behavior", "wrong track"),
            ]
        },
    )

    with pytest.raises(native.NativeScenarioValidationError) as exc_info:
        native.finalize(work_dir)

    assert set(exc_info.value.failures) == {"attack"}
    assert not (work_dir / "candidates.json").exists()


@pytest.mark.parametrize(
    ("role", "limit"),
    [("attack", 6), ("behavior", 3), ("persistence", 3)],
)
def test_finalize_rejects_role_output_above_scenario_limit(
    tmp_path: Path,
    role: Literal["attack", "behavior", "persistence"],
    limit: int,
) -> None:
    work_dir = tmp_path / ".datarobot" / "swarm"
    write_role_outputs(work_dir)
    artifacts.write_json(
        work_dir / f"{role}-output.json",
        {
            "scenarios": [
                proposal_data(role, f"{role} scenario {index}")
                for index in range(limit + 1)
            ]
        },
    )

    with pytest.raises(native.NativeScenarioValidationError) as exc_info:
        native.finalize(work_dir)

    assert exc_info.value.failures[role].endswith(f"maximum is {limit}")
    assert not (work_dir / "candidates.json").exists()


def test_finalize_cli_reports_failed_role(tmp_path: Path) -> None:
    work_dir = tmp_path / ".datarobot" / "swarm"
    write_role_outputs(work_dir)
    (work_dir / "attack-output.json").write_text("{invalid", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "finalize",
            "--work-dir",
            str(work_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert result.stderr.startswith("role:attack validation failed:")
    assert "role:behavior" not in result.stderr
    assert not (work_dir / "candidates.json").exists()


def test_confirm_applies_review_edits_and_assigns_ids(tmp_path: Path) -> None:
    work_dir = tmp_path / ".datarobot" / "swarm"
    write_role_outputs(work_dir)
    candidates = native.finalize(work_dir)
    reviewed = candidates.model_dump(mode="json")
    reviewed["scenarios"] = [
        scenario
        for scenario in reviewed["scenarios"]
        if scenario["track"] != "behavior"
    ]
    reviewed["scenarios"].append(
        proposal_data("behavior", "user-added behavior scenario")
    )
    artifacts.write_json(work_dir / "candidates.json", reviewed)
    criteria_path = tmp_path / "evaluation_criteria.md"

    confirmed = native.confirm(work_dir, criteria_path)

    assert len(confirmed) == 3
    assert {scenario.name for scenario in confirmed} == {
        "attack scenario",
        "persistence scenario",
        "user-added behavior scenario",
    }
    loaded = artifacts.load_criteria(criteria_path)
    assert all(scenario.scenario_id for scenario in loaded)


def test_confirm_rejects_duplicate_scenarios_without_overwriting(
    tmp_path: Path,
) -> None:
    work_dir = tmp_path / ".datarobot" / "swarm"
    duplicate = proposal_data("attack", "duplicate")
    artifacts.write_json(
        work_dir / "candidates.json", {"scenarios": [duplicate, duplicate]}
    )
    criteria_path = tmp_path / "evaluation_criteria.md"
    criteria_path.write_text("existing", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate scenario"):
        native.confirm(work_dir, criteria_path)

    assert criteria_path.read_text(encoding="utf-8") == "existing"


def test_skill_documents_native_generation_state_transitions() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "Run each generator one at a time" in skill
    assert "gateway_worker.py" in skill
    assert "native_scenarios.py configure" in skill
    assert "native_scenarios.py prepare" in skill
    assert "native_scenarios.py finalize" in skill
    assert "native_scenarios.py confirm" in skill
    assert "Read `finalize` stdout and present the candidate list" in skill
    assert '--rejection-note "<reason>"' in skill


def test_skill_is_cut_over_to_native_execution_and_convergence() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "native_swarm.py run" in skill
    assert "native_execution.py submit" in skill
    assert "native_execution.py fail" in skill
    assert "native_convergence.py initialize" in skill
    assert "native_convergence.py advance" in skill
    assert "native_convergence.py report" in skill
    assert "Run each generator one at a time" in skill
    assert "Convergence complete" in skill
    assert "dr opencode models" in skill
    assert "swarm_simulation.py" not in skill
    assert "pydantic_ai" not in skill
    assert "dr auth check" in skill
    assert "--model" in skill
