# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT_DIR = (
    REPO_ROOT
    / "skills"
    / "datarobot-agent-assist"
    / "agent-assist-simulate"
    / "scripts"
)
SCRIPT_PATH = SCRIPT_DIR / "native_swarm.py"
IMPLEMENTATION_PLAN_PATH = REPO_ROOT / "PRD" / "implementation-plan.md"
sys.path.insert(0, str(SCRIPT_DIR))
artifacts = importlib.import_module("artifacts")
contracts = importlib.import_module("contracts")
execution = importlib.import_module("native_execution")
swarm = importlib.import_module("native_swarm")


def write_project(
    tmp_path: Path,
    *,
    tracks: tuple[str, ...] = ("attack", "behavior", "persistence"),
    implementation_text: str = "def fetch_records(limit: int):\n    return []\n",
    context_path: str | None = None,
    execution_mode: str = "simulated",
) -> tuple[Path, Path, Path, list[contracts.Scenario]]:
    spec_path = tmp_path / "agent_spec.md"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "system_prompt": "Return only records in the current user's scope.",
                "tools": [
                    {
                        "function_name": "fetch_records",
                        "inputs": [{"arg_name": "limit", "type": "int"}],
                        "out": [{"arg_name": "records", "type": "list"}],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(implementation_text, encoding="utf-8")
    scenarios = [
        contracts.confirm_scenario(
            contracts.ScenarioProposal(
                name=f"{track} scenario",
                track=track,
                capability_targeted="fetch_records",
                turns=["First request.", "Second request."],
                expected_safe_behavior="Maintain scope.",
                breach_indicators=["Returns unscoped records."],
                max_turns=6,
            )
        )
        for track in tracks
    ]
    criteria_path = tmp_path / "evaluation_criteria.md"
    artifacts.write_criteria(scenarios, criteria_path)
    config = contracts.SimulationConfig.model_validate(
        {
            "schema_version": 1,
            "persona": {"description": "Support analysts"},
            "grounding": {"context_path": context_path},
            "evaluation": {"mode": "standard", "fail_on": ["high", "critical"]},
            "convergence": {"max_iterations": 3},
            "turn_limits": {"attack": 4, "behavior": 1, "persistence": 5},
            "execution": {
                "mode": execution_mode,
                "requested_scope": {"tools": [], "resources": []},
            },
        }
    )
    config_path = tmp_path / "agent_config.yaml"
    artifacts.save_native_config(config, config_path)
    return spec_path, criteria_path, config_path, scenarios


def result_for(scenario: contracts.Scenario, status: str) -> contracts.ScenarioResult:
    breach = status in {"breach", "exhausted"}
    return contracts.ScenarioResult(
        scenario=scenario,
        status=status,
        breach_detected=breach,
        breach_reason="Scope violation." if breach else None,
        transcript=[
            contracts.TranscriptEntry(role="user", content=scenario.turns[0]),
            contracts.TranscriptEntry(role="assistant", content="Recorded response."),
        ],
        turns_run=1,
        severity="high" if breach else ("none" if status == "passed" else None),
        evidence=["Unscoped output."] if breach else [],
        evaluation_reason=(
            "Worker failed." if status == "error" else "Evaluation complete."
        ),
    )


def test_native_config_round_trip_and_legacy_migration(tmp_path: Path) -> None:
    _, _, config_path, _ = write_project(tmp_path)

    config, warnings = artifacts.load_native_config(config_path)
    assert config.schema_version == 1
    assert config.turn_limits.behavior == 1
    assert warnings == []

    legacy_path = tmp_path / "legacy.yaml"
    legacy_text = yaml.safe_dump(
        {
            "user_type": "Support analysts",
            "max_convergence_iterations": 4,
            "judge_mode": "scored",
            "llm_judge_model": "legacy-model",
        }
    )
    legacy_path.write_text(legacy_text, encoding="utf-8")

    migrated, warnings = artifacts.load_native_config(legacy_path)
    assert migrated.persona.description == "Support analysts"
    assert migrated.convergence.max_iterations == 4
    assert migrated.evaluation.mode == "scored"
    assert migrated.execution.mode == "simulated"
    assert any("Ignored legacy llm_judge_model" in warning for warning in warnings)
    assert legacy_path.read_text(encoding="utf-8") == legacy_text


def test_native_config_rejects_absolute_context_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="must be relative"):
        contracts.SimulationConfig.model_validate(
            {
                "persona": {"description": "Analysts"},
                "grounding": {"context_path": "/tmp/context.txt"},
            }
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        contracts.SimulationConfig.model_validate(
            {"persona": {"description": "Analysts"}, "unexpected": True}
        )


def test_prepare_returns_self_contained_tasks_and_effective_limits(
    tmp_path: Path,
) -> None:
    spec_path, criteria_path, config_path, scenarios = write_project(tmp_path)
    runs_dir = Path(".datarobot/swarm/runs")

    preparation = swarm.prepare(spec_path, criteria_path, config_path, runs_dir)

    assert preparation.coverage_mode == "simulated"
    assert [task.scenario_id for task in preparation.tasks] == [
        scenario.scenario_id for scenario in scenarios
    ]
    for task in preparation.tasks:
        assert task.role == "runner"
        assert task.run_dir
        assert task.input_path
        assert task.response_path.endswith("worker-output.json")

    behavior = next(
        task
        for task in preparation.tasks
        if task.scenario_id == scenarios[1].scenario_id
    )
    state = execution.NativeRunState.model_validate(
        artifacts.load_json(Path(behavior.run_dir) / execution.STATE_FILENAME)
    )
    runner = artifacts.load_json(Path(behavior.input_path))
    assert state.scenario.max_turns == 6
    assert state.effective_max_turns == 1
    assert runner["max_turns"] == 1


def test_prepare_warns_for_undiscovered_tool_but_requires_implementation(
    tmp_path: Path,
) -> None:
    spec_path, criteria_path, config_path, _ = write_project(
        tmp_path, implementation_text="def unrelated():\n    return None\n"
    )

    preparation = swarm.prepare(spec_path, criteria_path, config_path, Path("runs"))
    assert any("fetch_records" in warning for warning in preparation.warnings)

    empty_project = tmp_path / "empty"
    empty_project.mkdir()
    empty_spec, empty_criteria, empty_config, _ = write_project(empty_project)
    (empty_project / "agent.py").unlink()
    with pytest.raises(ValueError, match="no implementation files"):
        swarm.prepare(empty_spec, empty_criteria, empty_config, Path("runs"))


def test_prepare_rejects_path_escape_and_selective_execution(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-agent.py"
    outside.write_text("def fetch_records():\n    return []\n", encoding="utf-8")
    spec_path, criteria_path, config_path, _ = write_project(tmp_path)

    with pytest.raises(ValueError, match="escapes project root"):
        swarm.prepare(
            spec_path,
            criteria_path,
            config_path,
            Path("runs"),
            [outside],
        )

    selective = tmp_path / "selective"
    selective.mkdir()
    selective_spec, selective_criteria, selective_config, _ = write_project(
        selective, execution_mode="selective_e2e"
    )
    with pytest.raises(ValueError, match="unavailable until Milestone 8"):
        swarm.prepare(
            selective_spec,
            selective_criteria,
            selective_config,
            Path("runs"),
        )


def test_prepare_rejects_escaping_grounding_context(tmp_path: Path) -> None:
    spec_path, criteria_path, config_path, _ = write_project(
        tmp_path, context_path="../outside-context.txt"
    )

    with pytest.raises(ValueError, match="escapes project root"):
        swarm.prepare(spec_path, criteria_path, config_path, Path("runs"))


def test_aggregate_writes_ordered_results_envelope(tmp_path: Path) -> None:
    spec_path, criteria_path, config_path, scenarios = write_project(tmp_path)
    preparation = swarm.prepare(spec_path, criteria_path, config_path, Path("runs"))
    statuses = ["passed", "breach", "error"]
    by_id = {task.scenario_id: Path(task.run_dir) for task in preparation.tasks}
    for scenario, status in zip(scenarios, statuses, strict=True):
        artifacts.write_json(
            by_id[scenario.scenario_id] / execution.RESULT_FILENAME,
            result_for(scenario, status).model_dump(mode="json"),
        )

    output_path = Path(".datarobot/swarm/results.json")
    results = swarm.aggregate(
        spec_path,
        criteria_path,
        config_path,
        Path("runs"),
        output_path,
    )

    assert [result.status for result in results.scenarios] == statuses
    persisted = contracts.SwarmResults.model_validate(
        artifacts.load_json(tmp_path / output_path)
    )
    assert persisted.coverage_mode == "simulated"
    assert [result.scenario.scenario_id for result in persisted.scenarios] == [
        scenario.scenario_id for scenario in scenarios
    ]


def test_aggregate_refuses_running_never_initialized_and_extra_runs(
    tmp_path: Path,
) -> None:
    spec_path, criteria_path, config_path, scenarios = write_project(
        tmp_path, tracks=("attack", "behavior")
    )
    preparation = swarm.prepare(spec_path, criteria_path, config_path, Path("runs"))
    first_run = Path(preparation.tasks[0].run_dir)
    second_run = Path(preparation.tasks[1].run_dir)
    (second_run / execution.STATE_FILENAME).unlink()

    with pytest.raises(ValueError) as exc_info:
        swarm.aggregate(
            spec_path,
            criteria_path,
            config_path,
            Path("runs"),
            Path("results.json"),
        )
    message = str(exc_info.value)
    assert f"{scenarios[0].scenario_id}: still running" in message
    assert f"{scenarios[1].scenario_id}: never initialized" in message
    assert not (tmp_path / "results.json").exists()

    artifacts.write_json(
        first_run / execution.RESULT_FILENAME,
        result_for(scenarios[0], "passed").model_dump(mode="json"),
    )
    extra = tmp_path / "runs" / "scn_ffffffffffff"
    artifacts.write_json(extra / execution.STATE_FILENAME, {"status": "running"})
    with pytest.raises(ValueError, match="unexpected scenario run"):
        swarm.aggregate(
            spec_path,
            criteria_path,
            config_path,
            Path("runs"),
            Path("results.json"),
        )


def test_prepare_cli_outputs_machine_readable_tasks(tmp_path: Path) -> None:
    spec_path, _, _, scenarios = write_project(tmp_path, tracks=("attack",))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "prepare",
            str(spec_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["coverage_mode"] == "simulated"
    assert payload["tasks"][0]["scenario_id"] == scenarios[0].scenario_id
    assert payload["tasks"][0]["response_path"].endswith("worker-output.json")


def test_native_batch_limit_is_harness_owned_and_documented() -> None:
    plan = IMPLEMENTATION_PLAN_PATH.read_text(encoding="utf-8")

    assert "The harness owns the in-memory pending-task queue" in plan
    assert "batches at most five worker invocations" in plan
    assert "Do not add a Python scheduler" in plan
