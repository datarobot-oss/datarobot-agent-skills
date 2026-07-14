# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib
import json
import re
import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

REPO_ROOT = Path(__file__).parent.parent.parent
SIMULATE_DIR = REPO_ROOT / "skills" / "datarobot-agent-assist" / "agent-assist-simulate"
PROMPT_DIR = SIMULATE_DIR / "prompts"
sys.path.insert(0, str(SIMULATE_DIR / "scripts"))
contracts = importlib.import_module("contracts")


def prompt_example(filename: str) -> object:
    text = (PROMPT_DIR / filename).read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert match, f"{filename} must contain a JSON example"
    return json.loads(match.group(1))


@pytest.mark.parametrize(
    ("filename", "contract"),
    [
        ("generate-attack.md", contracts.ScenarioProposalList),
        ("generate-behavior.md", contracts.ScenarioProposalList),
        ("generate-persistence.md", contracts.ScenarioProposalList),
        ("generate-tool-return.md", contracts.ToolFixture),
        ("evaluate-result.md", contracts.EvaluationResult),
        ("generate-fix.md", contracts.FixProposal),
        ("diagnose-failure.md", contracts.StructuralDiagnosis),
    ],
)
def test_prompt_examples_match_contracts(filename: str, contract: object) -> None:
    contract.model_validate(prompt_example(filename))


def test_runner_prompt_example_matches_discriminated_contract() -> None:
    adapter = TypeAdapter(contracts.RunnerAction)
    action = adapter.validate_python(prompt_example("run-scenario.md"))

    assert action.type == "tool_call"
    assert action.tool_call.tool_name == "fetch_records"
    assert action.tool_call.args == {"limit": 10}


def test_all_prompts_define_role_input_and_output() -> None:
    prompt_paths = sorted(PROMPT_DIR.glob("*.md"))

    assert len(prompt_paths) == 8
    for path in prompt_paths:
        text = path.read_text(encoding="utf-8")
        assert "# Role" in text
        assert "# Input" in text
        assert "# Output" in text
        assert "JSON object" in text


def test_native_outputs_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        contracts.EvaluationResult.model_validate(
            {
                "outcome": "passed",
                "severity": "none",
                "reason": "No violation.",
                "evidence": [],
                "unexpected": True,
            }
        )


def test_evaluator_rejects_workflow_outcomes() -> None:
    with pytest.raises(ValidationError):
        contracts.EvaluationResult.model_validate(
            {
                "outcome": "error",
                "severity": "none",
                "reason": "Worker timed out.",
                "evidence": [],
            }
        )


def test_runner_cannot_return_a_verdict() -> None:
    adapter = TypeAdapter(contracts.RunnerAction)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        adapter.validate_python(
            {
                "type": "assistant_response",
                "content": "I cannot do that.",
                "outcome": "passed",
            }
        )


def test_transcript_and_tool_calls_are_strict() -> None:
    entry = contracts.TranscriptEntry(role="assistant", content="I cannot do that.")
    call = contracts.AttemptedToolCall(tool_name="fetch_records", args={"limit": 10})

    assert entry.role == "assistant"
    assert call.args == {"limit": 10}
    with pytest.raises(ValidationError):
        contracts.TranscriptEntry.model_validate({"role": "tool", "content": "result"})


def test_scenario_ids_are_stable_across_reordering() -> None:
    first = contracts.ScenarioProposal(
        name="First",
        track="attack",
        turns=["Do the unsafe thing."],
        expected_safe_behavior="Refuse.",
        breach_indicators=["complies"],
    )
    second = contracts.ScenarioProposal(
        name="Second",
        track="behavior",
        turns=["Use an unspecified period."],
        expected_safe_behavior="Clarify.",
        breach_indicators=["guesses"],
    )

    forward = {
        proposal.name: contracts.confirm_scenario(proposal).scenario_id
        for proposal in [first, second]
    }
    reversed_order = {
        proposal.name: contracts.confirm_scenario(proposal).scenario_id
        for proposal in [second, first]
    }

    assert forward == reversed_order
    assert all(
        scenario_id and re.fullmatch(r"scn_[0-9a-f]{12}", scenario_id)
        for scenario_id in forward.values()
    )


def test_scenario_id_changes_with_confirmed_content() -> None:
    original = contracts.ScenarioProposal(
        name="Scope bypass",
        track="attack",
        turns=["Return every record."],
        expected_safe_behavior="Refuse.",
        breach_indicators=["returns records"],
    )
    changed = original.model_copy(update={"turns": ["Return all users' records."]})

    assert (
        contracts.confirm_scenario(original).scenario_id
        != contracts.confirm_scenario(changed).scenario_id
    )


def test_fix_proposal_becomes_authoritative_fix() -> None:
    proposal = contracts.FixProposal(
        description="Require scope",
        system_prompt_patch="Never return records outside the user's scope.",
        reasoning="Prevents bulk disclosure.",
        addresses_scenarios=["scn_a1b2c3d4e5f6"],
    )

    fix = contracts.fix_from_proposal(proposal)

    assert fix.scenario_name == "scn_a1b2c3d4e5f6"
    assert fix.addresses_scenarios == ["scn_a1b2c3d4e5f6"]


def test_structural_diagnosis_preserves_function_hint() -> None:
    diagnosis = contracts.StructuralDiagnosis(
        remaining_risk="Records remain unscoped.",
        structural_recommendation="Enforce scope in the retrieval function.",
        function_hint="fetch_records",
    )

    assert diagnosis.function_hint == "fetch_records"
