# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Shared contract helpers for agent-assist integration tests.

Field rules mirror resume-design.md § Spec complete and llm-selection.md.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

EXAMPLES_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills/datarobot-agent-assist/agent-assist-build/references/agent-spec-examples.md"
)

# Shaped as /genai/llmgw/catalog/ returns them.
GATEWAY_CATALOG_ENTRY = {
    "llmId": "azure-openai-gpt-5",
    "model": "azure/gpt-5-2025-08-07",
    "name": "Azure OpenAI GPT-5",
    "provider": "Azure OpenAI",
    "contextSize": 400000,
    "isActive": True,
}

CLI_ENTRY = {
    "id": "azure-openai-gpt-5",
    "name": "Azure OpenAI GPT-5",
    "provider": "Azure OpenAI",
    "model": "azure/gpt-5-2025-08-07",
    "source": "gateway",
}

DEPLOYED_CATALOG_ENTRY = {
    "id": "6a43eb5f10dbecadbebc5b2b",
    "label": "DocsBot (stg)",
    "status": "active",
    "model": {"targetType": "TextGeneration"},
}

LLM_ID = "azure-openai-gpt-5"
API_MODEL = "azure/gpt-5-2025-08-07"
CANONICAL = "datarobot/azure/gpt-5-2025-08-07"
DEPLOYED_PLACEHOLDER = "datarobot/datarobot-deployed-llm"

CATALOG_PROVIDERS = {"anthropic", "azure", "bedrock", "vertex_ai"}

DEPLOYED_ROUTING_KEYS = (
    'LLM_DEPLOYMENT_ID="',
    'INFRA_ENABLE_LLM="deployed_llm.py"',
    'USE_DATAROBOT_LLM_GATEWAY="0"',
)

_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


def parse_yaml_blocks(markdown: str) -> list[dict[str, Any]]:
    """Extract and parse every ```yaml block from a markdown file."""
    specs: list[dict[str, Any]] = []
    for match in _YAML_BLOCK_RE.finditer(markdown):
        loaded = yaml.safe_load(match.group(1))
        if isinstance(loaded, dict):
            specs.append(loaded)
    return specs


def load_spec_examples() -> list[dict[str, Any]]:
    return parse_yaml_blocks(EXAMPLES_PATH.read_text(encoding="utf-8"))


def map_gateway_listing(list_llm_models: Any) -> dict[str, Any]:
    mapped = list_llm_models._map_gateway_catalog_entry(GATEWAY_CATALOG_ENTRY)
    assert mapped is not None
    return dict(mapped)


def map_deployed_listing(list_llm_models: Any) -> dict[str, Any]:
    mapped = list_llm_models._map_deployed_entry(DEPLOYED_CATALOG_ENTRY)
    assert mapped is not None
    return dict(mapped)


def is_valid_spec_model(model: str, list_llm_models: Any) -> bool:
    """Whether ``model`` is an acceptable ``agent_spec.md`` value."""
    value = model.strip()
    if not value:
        return False
    if list_llm_models.is_deployed_llm_model(value):
        return True
    if not value.startswith("datarobot/"):
        return False
    bare = list_llm_models.normalize_gateway_model(value)
    return "/" in bare


def validate_spec_complete(spec: dict[str, Any], list_llm_models: Any) -> list[str]:
    """Return human-readable errors; empty list means the spec is coding-ready."""
    errors: list[str] = []

    system_prompt = spec.get("system_prompt")
    if system_prompt is None or not str(system_prompt).strip():
        errors.append("missing or empty system_prompt")

    model = spec.get("model")
    if model is None or not str(model).strip():
        errors.append("missing or empty model")
    elif not is_valid_spec_model(str(model), list_llm_models):
        errors.append(f"invalid model value: {model!r}")

    frontend = spec.get("frontend")
    if not isinstance(frontend, dict) or not str(frontend.get("type") or "").strip():
        errors.append("missing frontend.type")

    if "tools" not in spec:
        errors.append("missing tools key")

    model_str = str(model or "").strip()
    if model_str and list_llm_models.is_deployed_llm_model(model_str):
        deployment_id = spec.get("llm_deployment_id")
        if deployment_id is None or not str(deployment_id).strip():
            errors.append("missing llm_deployment_id for deployed placeholder model")
        elif not list_llm_models.is_deployment_id(str(deployment_id)):
            errors.append(f"invalid llm_deployment_id: {deployment_id!r}")

    return errors


def spec_fields_from_listing_entry(entry: dict[str, Any]) -> dict[str, str]:
    """Fields an agent must write to agent_spec.md for a listing entry."""
    model = str(entry["llm_default_model"])
    if entry.get("source") == "deployed":
        deployment_id = str(entry["deployment_id"])
        return {"model": model, "llm_deployment_id": deployment_id}
    return {"model": model}
