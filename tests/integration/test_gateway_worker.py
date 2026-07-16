# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = (
    REPO_ROOT
    / "skills"
    / "datarobot-agent-assist"
    / "agent-assist-simulate"
    / "scripts"
    / "gateway_worker.py"
)
SPEC = importlib.util.spec_from_file_location("gateway_worker", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
gateway_worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gateway_worker)


def test_scenario_id_from_runner_input(tmp_path: Path) -> None:
    input_path = tmp_path / "runner-input.json"
    input_path.write_text(
        json.dumps({"scenario_id": "scn_040a81e85e34"}),
        encoding="utf-8",
    )

    assert gateway_worker._scenario_id_from_input(input_path) == "scn_040a81e85e34"


def test_scenario_id_from_diagnoser_input(tmp_path: Path) -> None:
    input_path = tmp_path / "diagnoser-input.json"
    input_path.write_text(
        json.dumps({"scenario": {"scenario_id": "scn_abc123456789"}}),
        encoding="utf-8",
    )

    assert gateway_worker._scenario_id_from_input(input_path) == "scn_abc123456789"


def test_write_metrics_creates_swarm_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_path = tmp_path / ".datarobot/swarm/metrics.jsonl"
    monkeypatch.setattr(gateway_worker, "METRICS_PATH", metrics_path)

    gateway_worker._write_metrics({"role": "runner", "success": True})

    assert metrics_path.is_file()
    record = json.loads(metrics_path.read_text(encoding="utf-8").strip())
    assert record["role"] == "runner"
    assert record["success"] is True
