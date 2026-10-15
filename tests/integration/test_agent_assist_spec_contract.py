# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for agent_spec.md completeness and model shape."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from agent_assist_contracts import (
    CANONICAL,
    CATALOG_PROVIDERS,
    DEPLOYED_PLACEHOLDER,
    load_spec_examples,
    validate_spec_complete,
)

_MINIMAL_GATEWAY_SPEC: dict[str, Any] = {
    "model": CANONICAL,
    "system_prompt": "You are a helpful assistant.",
    "tools": [
        {
            "function_name": "lookup",
            "inputs": [{"arg_name": "query", "type": "str"}],
            "out": [{"arg_name": "result", "type": "str"}],
        }
    ],
    "frontend": {"type": "chat"},
}


def _validate(spec: dict[str, Any], list_llm_models: Any) -> list[str]:
    return validate_spec_complete(spec, list_llm_models)


def _without(spec: dict[str, Any], *keys: str) -> dict[str, Any]:
    trimmed = copy.deepcopy(spec)
    for key in keys:
        trimmed.pop(key, None)
    return trimmed


@pytest.mark.parametrize(
    "spec",
    [
        pytest.param(_MINIMAL_GATEWAY_SPEC, id="minimal_gateway"),
        pytest.param({**_MINIMAL_GATEWAY_SPEC, "tools": []}, id="explicit_empty_tools"),
    ],
)
def test_spec_complete_accepts_valid_specs(
    spec: dict[str, Any], list_llm_models: Any
) -> None:
    assert _validate(spec, list_llm_models) == []


@pytest.mark.parametrize(
    ("spec", "expected_errors"),
    [
        pytest.param(
            _without(_MINIMAL_GATEWAY_SPEC, "system_prompt"),
            ["missing or empty system_prompt"],
            id="missing_system_prompt",
        ),
        pytest.param(
            _without(_MINIMAL_GATEWAY_SPEC, "model"),
            ["missing or empty model"],
            id="missing_model",
        ),
        pytest.param(
            _without(_MINIMAL_GATEWAY_SPEC, "frontend"),
            ["missing frontend.type"],
            id="missing_frontend",
        ),
        pytest.param(
            _without(_MINIMAL_GATEWAY_SPEC, "tools"),
            ["missing tools key"],
            id="missing_tools_key",
        ),
        pytest.param(
            {
                **_MINIMAL_GATEWAY_SPEC,
                "model": DEPLOYED_PLACEHOLDER,
                "llm_deployment_id": "",
            },
            ["missing llm_deployment_id for deployed placeholder model"],
            id="placeholder_without_deployment_id",
        ),
        pytest.param(
            {**_MINIMAL_GATEWAY_SPEC, "model": "azure/gpt-5-2025-08-07"},
            ["invalid model value: 'azure/gpt-5-2025-08-07'"],
            id="bare_api_model",
        ),
        pytest.param(
            {**_MINIMAL_GATEWAY_SPEC, "model": "azure-openai-gpt-5"},
            ["invalid model value: 'azure-openai-gpt-5'"],
            id="catalog_llm_id",
        ),
    ],
)
def test_spec_complete_rejects_invalid_specs(
    spec: dict[str, Any],
    expected_errors: list[str],
    list_llm_models: Any,
) -> None:
    assert _validate(spec, list_llm_models) == expected_errors


def test_spec_examples_satisfy_contract(list_llm_models: Any) -> None:
    examples = load_spec_examples()
    assert examples, "no yaml examples found in agent-spec-examples.md"

    has_deployed_example = False
    for index, spec in enumerate(examples, start=1):
        errors = _validate(spec, list_llm_models)
        assert errors == [], f"example {index} failed spec_complete: {errors}"

        model = str(spec["model"])
        assert model.startswith("datarobot/"), f"{model} is missing the prefix"

        if list_llm_models.is_deployed_llm_model(model):
            has_deployed_example = True
            assert list_llm_models.is_deployment_id(
                str(spec.get("llm_deployment_id") or "")
            )
            continue

        bare = list_llm_models.normalize_gateway_model(model)
        provider = bare.split("/", 1)[0]
        assert provider in CATALOG_PROVIDERS, f"{model} names no real provider"

    assert has_deployed_example, (
        "agent-spec-examples.md must include at least one deployed-LLM example"
    )
