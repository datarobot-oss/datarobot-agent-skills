# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for how an agent should record LLM choices in agent_spec.md."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

from agent_assist_contracts import spec_fields_from_listing_entry

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills/datarobot-agent-assist/agent-assist-build/scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

list_llm_models = importlib.import_module("list_llm_models")

GATEWAY_ENTRY = {
    "llmId": "azure-openai-gpt-5",
    "model": "azure/gpt-5-2025-08-07",
    "name": "Azure OpenAI GPT-5",
    "provider": "Azure OpenAI",
    "contextSize": 400000,
    "isActive": True,
}

DEPLOYED_ENTRY = {
    "id": "6a43eb5f10dbecadbebc5b2b",
    "label": "DocsBot (stg)",
    "status": "active",
    "model": {"targetType": "TextGeneration"},
}

CANONICAL = "datarobot/azure/gpt-5-2025-08-07"
LLM_ID = "azure-openai-gpt-5"


def _gateway_listing() -> dict[str, Any]:
    mapped = list_llm_models._map_gateway_catalog_entry(GATEWAY_ENTRY)
    assert mapped is not None
    return dict(mapped)


def _deployed_listing() -> dict[str, Any]:
    mapped = list_llm_models._map_deployed_entry(DEPLOYED_ENTRY)
    assert mapped is not None
    return dict(mapped)


@pytest.mark.parametrize(
    ("listing_entry", "expected_fields", "forbidden_model_values"),
    [
        pytest.param(
            _gateway_listing(),
            {"model": CANONICAL},
            {LLM_ID, "azure/gpt-5-2025-08-07"},
            id="gateway",
        ),
        pytest.param(
            _deployed_listing(),
            {
                "model": "datarobot/datarobot-deployed-llm",
                "llm_deployment_id": DEPLOYED_ENTRY["id"],
            },
            set(),
            id="deployed",
        ),
    ],
)
def test_agent_records_llm_choice_in_spec(
    listing_entry: dict[str, Any],
    expected_fields: dict[str, str],
    forbidden_model_values: set[str],
) -> None:
    recorded = spec_fields_from_listing_entry(listing_entry)
    assert recorded == expected_fields
    assert recorded["model"] == listing_entry["llm_default_model"]
    assert recorded["model"] not in forbidden_model_values
    if listing_entry["source"] == "gateway":
        assert "llm_deployment_id" not in recorded
        assert recorded["model"] != listing_entry["id"]
        assert recorded["model"] != listing_entry["api_model"]
