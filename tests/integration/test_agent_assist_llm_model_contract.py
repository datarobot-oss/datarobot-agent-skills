# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for the model name the agent-assist build skill writes to .env.

The real-world bug: the skill wrote the LLM Gateway catalog's ``llmId``
(``azure-openai-gpt-5``) into ``LLM_DEFAULT_MODEL``, where the contract is
``datarobot/`` plus the catalog's ``model`` field
(``datarobot/azure/gpt-5-2025-08-07``). The gateway answers 404 for an llmId, so
every app built from that .env failed. Both values look equally plausible in a
record that carries them side by side, which is how an agent picked the wrong one.

The contract these tests hold:

  - the listing carries the canonical value in its own ``llm_default_model`` field
  - ``api_model`` stays unprefixed, because rehearsal.py puts it on the wire and
    the gateway rejects a ``datarobot/``-prefixed model
  - an llmId never reaches .env
  - the rehearsal still resolves the canonical value, so writing it costs nothing

Nothing here touches the network. Catalog payloads are fixtures.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills/datarobot-agent-assist/agent-assist-build/scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

list_llm_models = importlib.import_module("list_llm_models")
rehearsal = importlib.import_module("rehearsal")
setup_template = importlib.import_module("setup_template")

# Shaped as /genai/llmgw/catalog/ returns them.
GATEWAY_ENTRY = {
    "llmId": "azure-openai-gpt-5",
    "model": "azure/gpt-5-2025-08-07",
    "name": "Azure OpenAI GPT-5",
    "provider": "Azure OpenAI",
    "contextSize": 400000,
    "isActive": True,
}

# Shaped as `dr llm-gateway list --output-format json` returns them.
CLI_ENTRY = {
    "id": "azure-openai-gpt-5",
    "name": "Azure OpenAI GPT-5",
    "provider": "Azure OpenAI",
    "model": "azure/gpt-5-2025-08-07",
    "source": "gateway",
}

DEPLOYED_ENTRY = {
    "id": "6a43eb5f10dbecadbebc5b2b",
    "label": "DocsBot (stg)",
    "status": "active",
    "model": {"targetType": "TextGeneration"},
}

LLM_ID = "azure-openai-gpt-5"
API_MODEL = "azure/gpt-5-2025-08-07"
CANONICAL = "datarobot/azure/gpt-5-2025-08-07"


@pytest.fixture
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the credential-free path so no test can reach a live instance."""
    monkeypatch.delenv("DATAROBOT_ENDPOINT", raising=False)
    monkeypatch.delenv("DATAROBOT_API_TOKEN", raising=False)


def _gateway_model() -> dict[str, Any]:
    mapped = list_llm_models._map_gateway_catalog_entry(GATEWAY_ENTRY)
    assert mapped is not None
    return dict(mapped)


# -- the listing ----------------------------------------------------------------


def test_gateway_entry_carries_the_canonical_env_value() -> None:
    assert _gateway_model()["llm_default_model"] == CANONICAL


def test_gateway_api_model_is_never_prefixed() -> None:
    """rehearsal.py sends api_model to the gateway, which 404s on a prefix."""
    assert _gateway_model()["api_model"] == API_MODEL


def test_llm_id_is_kept_out_of_the_env_value() -> None:
    """The regression itself: the llmId must not be what lands in .env."""
    model = _gateway_model()
    assert model["id"] == LLM_ID
    assert LLM_ID not in model["llm_default_model"]


def test_cli_and_rest_mappers_agree() -> None:
    """The CLI is the primary source; a divergence here reintroduces the bug."""
    from_cli = list_llm_models._map_cli_entry(CLI_ENTRY)
    assert from_cli is not None
    assert from_cli["llm_default_model"] == _gateway_model()["llm_default_model"]
    assert from_cli["api_model"] == _gateway_model()["api_model"]


def test_deployed_entry_uses_the_prefixed_placeholder() -> None:
    mapped = list_llm_models._map_deployed_entry(DEPLOYED_ENTRY)
    assert mapped is not None
    assert mapped["llm_default_model"] == "datarobot/datarobot-deployed-llm"
    assert mapped["api_model"] == "datarobot-deployed-llm"


def test_prefixing_is_idempotent() -> None:
    once = list_llm_models.ensure_datarobot_prefix(API_MODEL)
    assert list_llm_models.ensure_datarobot_prefix(once) == once


# -- the table ------------------------------------------------------------------


def test_table_leads_with_the_env_value_not_the_llm_id() -> None:
    table = list_llm_models.format_as_table([_gateway_model()])
    header = table.splitlines()[0]
    assert header.startswith("LLM_DEFAULT_MODEL")
    assert CANONICAL in table
    # The llmId is the value the gateway rejects; showing it invites the mistake.
    assert LLM_ID not in table


def test_table_hides_the_deployment_column_when_all_gateway() -> None:
    deployed = list_llm_models._map_deployed_entry(DEPLOYED_ENTRY)
    assert deployed is not None
    gateway_only = list_llm_models.format_as_table([_gateway_model()])
    mixed = list_llm_models.format_as_table([_gateway_model(), deployed])
    assert "Deployment ID" not in gateway_only
    assert "Deployment ID" in mixed
    assert DEPLOYED_ENTRY["id"] in mixed


# -- what reaches .env ----------------------------------------------------------


def test_llm_id_is_refused(tmp_path: Path, no_credentials: None) -> None:
    """The exact field failure that broke the workshop."""
    assert setup_template.canonical_gateway_model(LLM_ID, tmp_path) is None


def test_unprefixed_model_is_canonicalized(
    tmp_path: Path, no_credentials: None
) -> None:
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) == CANONICAL


def test_already_canonical_value_survives(tmp_path: Path, no_credentials: None) -> None:
    assert setup_template.canonical_gateway_model(CANONICAL, tmp_path) == CANONICAL


def test_catalog_lookup_wins_on_spelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With credentials, the catalog is the authority on the exact spelling."""
    monkeypatch.setenv("DATAROBOT_ENDPOINT", "https://example.invalid/api/v2")
    monkeypatch.setenv("DATAROBOT_API_TOKEN", "token")
    monkeypatch.setattr(
        setup_template, "fetch_llm_models", lambda *_: [_gateway_model()]
    )
    assert (
        setup_template.canonical_gateway_model(API_MODEL.upper(), tmp_path) == CANONICAL
    )


def test_model_absent_from_catalog_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATAROBOT_ENDPOINT", "https://example.invalid/api/v2")
    monkeypatch.setenv("DATAROBOT_API_TOKEN", "token")
    monkeypatch.setattr(
        setup_template, "fetch_llm_models", lambda *_: [_gateway_model()]
    )
    assert (
        setup_template.canonical_gateway_model("azure/retired-model", tmp_path) is None
    )


def test_unreachable_catalog_does_not_block_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An instance this process cannot reach must not stop a scaffold."""
    monkeypatch.setenv("DATAROBOT_ENDPOINT", "https://example.invalid/api/v2")
    monkeypatch.setenv("DATAROBOT_API_TOKEN", "token")

    def _boom(*_: object) -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(setup_template, "fetch_llm_models", _boom)
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) == CANONICAL


def test_env_file_carries_the_canonical_value(tmp_path: Path) -> None:
    ok, _ = setup_template.create_env_file(tmp_path, CANONICAL)
    assert ok
    assert f'LLM_DEFAULT_MODEL="{CANONICAL}"' in (tmp_path / ".env").read_text()


# -- the rehearsal still resolves it --------------------------------------------


def test_rehearsal_resolves_the_canonical_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Writing the prefixed form must not cost an exact match in the rehearsal."""
    monkeypatch.setattr(rehearsal, "fetch_llm_models", lambda *_: [_gateway_model()])
    catalog = rehearsal.ModelCatalog("token", "https://example.invalid/api/v2")

    resolved, substituted = catalog.pick_available(CANONICAL)

    assert substituted is False
    # Still the bare form on the wire, whatever spelling the spec carried.
    assert resolved.api_model == API_MODEL
