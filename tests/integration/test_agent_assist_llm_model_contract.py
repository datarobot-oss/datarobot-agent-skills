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

from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import list_llm_models
import pytest
import rehearsal
import setup_template
from agent_assist_contracts import (
    API_MODEL,
    CANONICAL,
    CLI_ENTRY,
    DEPLOYED_CATALOG_ENTRY,
    DEPLOYED_PLACEHOLDER,
    DEPLOYED_ROUTING_KEYS,
    GATEWAY_CATALOG_ENTRY,
    LLM_ID,
    map_deployed_listing,
    map_gateway_listing,
    spec_fields_from_listing_entry,
)

DEPLOYED_ENTRY = DEPLOYED_CATALOG_ENTRY
GATEWAY_ENTRY = GATEWAY_CATALOG_ENTRY


@pytest.fixture
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the credential-free path so no test can reach a live instance."""
    monkeypatch.delenv("DATAROBOT_ENDPOINT", raising=False)
    monkeypatch.delenv("DATAROBOT_API_TOKEN", raising=False)


def _gateway_model() -> dict[str, Any]:
    return map_gateway_listing(list_llm_models)


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
    mapped = map_deployed_listing(list_llm_models)
    assert mapped["llm_default_model"] == DEPLOYED_PLACEHOLDER
    assert mapped["api_model"] == "datarobot-deployed-llm"


def test_prefixing_is_idempotent() -> None:
    once = list_llm_models.ensure_datarobot_prefix(API_MODEL)
    assert list_llm_models.ensure_datarobot_prefix(once) == once


@pytest.mark.parametrize(
    ("listing_entry", "expected_fields"),
    [
        pytest.param(
            map_gateway_listing(list_llm_models),
            {"model": CANONICAL},
            id="gateway",
        ),
        pytest.param(
            map_deployed_listing(list_llm_models),
            {
                "model": DEPLOYED_PLACEHOLDER,
                "llm_deployment_id": DEPLOYED_ENTRY["id"],
            },
            id="deployed",
        ),
    ],
)
def test_listing_entry_maps_to_spec_fields(
    listing_entry: dict[str, Any],
    expected_fields: dict[str, str],
) -> None:
    recorded = spec_fields_from_listing_entry(listing_entry)
    assert recorded == expected_fields
    assert recorded["model"] == listing_entry["llm_default_model"]
    if listing_entry["source"] == "gateway":
        assert recorded["model"] not in {
            listing_entry["id"],
            listing_entry["api_model"],
        }


# -- the table ------------------------------------------------------------------


def test_table_leads_with_the_env_value_not_the_llm_id() -> None:
    header, _rule, row = list_llm_models.format_as_table(
        [_gateway_model()]
    ).splitlines()
    assert header.split("|")[0].strip() == "LLM_DEFAULT_MODEL"
    assert row.split("|")[0].strip() == CANONICAL


def test_table_hides_the_deployment_column_when_all_gateway() -> None:
    deployed = map_deployed_listing(list_llm_models)
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


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Stand in for the instance's gateway catalog, with credentials present."""
    monkeypatch.setenv("DATAROBOT_ENDPOINT", "https://example.invalid/api/v2")
    monkeypatch.setenv("DATAROBOT_API_TOKEN", "token")

    def _serve(
        entries: list[Any] | BaseException, cause: BaseException | None = None
    ) -> None:
        def _fetch(*_: object) -> list[Any]:
            if isinstance(entries, BaseException):
                raise entries from cause
            return entries

        monkeypatch.setattr(setup_template, "_fetch_gateway_models_rest", _fetch)

    return _serve


def test_catalog_lookup_wins_on_spelling(tmp_path: Path, catalog: Any) -> None:
    catalog([_gateway_model()])
    assert (
        setup_template.canonical_gateway_model(API_MODEL.upper(), tmp_path) == CANONICAL
    )


def test_catalog_overrules_the_slash_heuristic(tmp_path: Path, catalog: Any) -> None:
    bare_name = dict(_gateway_model())
    bare_name["api_model"] = "gpt-4o"
    bare_name["llm_default_model"] = "datarobot/gpt-4o"
    catalog([bare_name])
    assert (
        setup_template.canonical_gateway_model("gpt-4o", tmp_path) == "datarobot/gpt-4o"
    )


def test_model_absent_from_catalog_is_refused(tmp_path: Path, catalog: Any) -> None:
    catalog([_gateway_model()])
    assert (
        setup_template.canonical_gateway_model("azure/retired-model", tmp_path) is None
    )


def test_catalog_present_still_refuses_a_bare_llm_id(
    tmp_path: Path, catalog: Any
) -> None:
    catalog([_gateway_model()])
    assert setup_template.canonical_gateway_model(LLM_ID, tmp_path) is None


def test_unreachable_catalog_does_not_block_setup(tmp_path: Path, catalog: Any) -> None:
    catalog(RuntimeError("connection refused"))
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) == CANONICAL


def test_connection_reset_does_not_block_setup(tmp_path: Path, catalog: Any) -> None:
    catalog(ConnectionResetError(54, "Connection reset by peer"))
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) == CANONICAL


def test_empty_gateway_points_at_a_deployed_llm(
    tmp_path: Path, catalog: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog([])
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) is None
    err = capsys.readouterr().err
    assert "--llm-deployment-id" in err
    assert "Available:" not in err


def test_disabled_gateway_is_treated_as_empty(
    tmp_path: Path, catalog: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    http_404 = HTTPError("https://x/api/v2/genai/llmgw/catalog/", 404, "", {}, None)  # type: ignore[arg-type]
    catalog(RuntimeError("Failed to fetch LLM Gateway catalog"), cause=http_404)
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) is None
    assert "--llm-deployment-id" in capsys.readouterr().err


def test_forbidden_catalog_is_not_a_disabled_gateway(
    tmp_path: Path, catalog: Any
) -> None:
    forbidden = HTTPError("https://x/api/v2/genai/llmgw/catalog/", 403, "", {}, None)  # type: ignore[arg-type]
    catalog(RuntimeError("Failed to fetch LLM Gateway catalog"), cause=forbidden)
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) == CANONICAL


def test_env_file_refuses_a_value_that_would_break_the_line(tmp_path: Path) -> None:
    ok, _ = setup_template.create_env_file(tmp_path, 'a/b" \nFOO="bar')
    assert not ok
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize("bad_char", ['"', "\\", "$", " ", "\n", "`"])
def test_env_file_rejects_each_dangerous_character(
    tmp_path: Path, bad_char: str
) -> None:
    ok, _ = setup_template.create_env_file(tmp_path, f"datarobot/azure/gpt-5{bad_char}")
    assert not ok
    assert not (tmp_path / ".env").exists()


def test_env_file_rejects_an_empty_model(tmp_path: Path) -> None:
    ok, _ = setup_template.create_env_file(tmp_path, "")
    assert not ok
    assert not (tmp_path / ".env").exists()


def test_env_file_accepts_every_shape_the_real_catalog_uses(tmp_path: Path) -> None:
    for model in (
        "datarobot/bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
        "datarobot/vertex_ai/claude-haiku-4-5@20251001",
        "datarobot/azure/gpt-5-2025-08-07",
        DEPLOYED_PLACEHOLDER,
    ):
        ok, msg = setup_template.create_env_file(tmp_path, model)
        assert ok, f"{model} rejected: {msg}"


@pytest.mark.parametrize(
    ("llm_model", "deployment_id", "expected_fragments", "forbidden_fragments"),
    [
        pytest.param(
            CANONICAL,
            "",
            [f'LLM_DEFAULT_MODEL="{CANONICAL}"'],
            DEPLOYED_ROUTING_KEYS,
            id="gateway",
        ),
        pytest.param(
            DEPLOYED_PLACEHOLDER,
            DEPLOYED_ENTRY["id"],
            [
                f'LLM_DEFAULT_MODEL="{DEPLOYED_PLACEHOLDER}"',
                f'LLM_DEPLOYMENT_ID="{DEPLOYED_ENTRY["id"]}"',
                'INFRA_ENABLE_LLM="deployed_llm.py"',
                'USE_DATAROBOT_LLM_GATEWAY="0"',
            ],
            (),
            id="deployed",
        ),
    ],
)
def test_create_env_file_writes_correct_routing_keys(
    tmp_path: Path,
    llm_model: str,
    deployment_id: str,
    expected_fragments: list[str],
    forbidden_fragments: tuple[str, ...],
) -> None:
    ok, _ = setup_template.create_env_file(tmp_path, llm_model, deployment_id)
    assert ok
    contents = (tmp_path / ".env").read_text()
    for fragment in expected_fragments:
        assert fragment in contents
    for fragment in forbidden_fragments:
        assert fragment not in contents


@pytest.mark.parametrize(
    ("llm_model", "deployment_id", "llm_base_url"),
    [
        pytest.param(
            DEPLOYED_PLACEHOLDER, "", "", id="placeholder_without_deployment_id"
        ),
        pytest.param(DEPLOYED_PLACEHOLDER, "null", "", id="invalid_deployment_id_null"),
        pytest.param(
            DEPLOYED_PLACEHOLDER,
            "not-a-valid-deployment-id",
            "",
            id="invalid_deployment_id_non_hex",
        ),
        pytest.param(
            "external-model",
            DEPLOYED_ENTRY["id"],
            "https://llm.example.invalid/v1",
            id="external_llm_with_deployment_id",
        ),
    ],
)
def test_setup_and_run_deployed_path_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    llm_model: str,
    deployment_id: str,
    llm_base_url: str,
) -> None:
    if llm_base_url:
        monkeypatch.setenv("AGENT_ASSIST_LLM_MODEL_NAME", "external-model")
        monkeypatch.setenv("AGENT_ASSIST_LLM_API_KEY", "test-key")
        monkeypatch.setenv("AGENT_ASSIST_LLM_BASE_URL", llm_base_url)

    assert (
        setup_template.setup_and_run(llm_model, tmp_path, deployment_id, llm_base_url)
        == 1
    )
    assert not (tmp_path / ".env").exists()


# -- the rehearsal still resolves it --------------------------------------------


def _model_catalog(monkeypatch: pytest.MonkeyPatch, entries: list[Any]) -> Any:
    monkeypatch.setattr(rehearsal, "fetch_llm_models", lambda *_: entries)
    return rehearsal.ModelCatalog("token", "https://example.invalid/api/v2")


def test_rehearsal_resolves_the_canonical_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_catalog = _model_catalog(monkeypatch, [_gateway_model()])
    resolved, substituted = model_catalog.pick_available(CANONICAL)
    assert substituted is False
    assert resolved.api_model == API_MODEL


def test_rehearsal_keeps_the_provider_guard_on_a_prefixed_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anthropic = list_llm_models._map_gateway_catalog_entry(
        {
            "llmId": "anthropic-1p-claude-sonnet-4-5",
            "model": "anthropic/claude-sonnet-4-5-20250929",
            "name": "Claude Sonnet 4.5",
            "provider": "Anthropic",
            "isActive": True,
        }
    )
    model_catalog = _model_catalog(monkeypatch, [_gateway_model(), anthropic])
    resolved, substituted = model_catalog.pick_available(
        "datarobot/anthropic/claude-sonnet-4.5-20250929"
    )
    assert substituted is True
    assert resolved.api_model == "anthropic/claude-sonnet-4-5-20250929"


def test_model_was_substituted_false_for_exact_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_catalog = _model_catalog(monkeypatch, [_gateway_model()])
    expected, _ = model_catalog.pick_available(CANONICAL)
    assert rehearsal._model_was_substituted(model_catalog, CANONICAL, expected) is False


def test_model_was_substituted_true_after_runtime_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anthropic = list_llm_models._map_gateway_catalog_entry(
        {
            "llmId": "anthropic-1p-claude-sonnet-4-5",
            "model": "anthropic/claude-sonnet-4-5-20250929",
            "name": "Claude Sonnet 4.5",
            "provider": "Anthropic",
            "isActive": True,
        }
    )
    model_catalog = _model_catalog(monkeypatch, [_gateway_model(), anthropic])
    expected, _ = model_catalog.pick_available(CANONICAL)
    fallback, _ = model_catalog.pick_available(CANONICAL, exclude_id=expected.id)
    assert rehearsal._model_was_substituted(model_catalog, CANONICAL, expected) is False
    assert rehearsal._model_was_substituted(model_catalog, CANONICAL, fallback) is True


def test_agent_model_was_substituted_uses_deployment_id_from_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployed = map_deployed_listing(list_llm_models)
    model_catalog = _model_catalog(monkeypatch, [_gateway_model(), deployed])
    config = {
        "requested_model": DEPLOYED_PLACEHOLDER,
        "requested_deployment_id": deployed["id"],
    }
    fallback, _ = model_catalog.pick_available(
        deployed["id"],
        prefer_source="deployed",
        exclude_id=deployed["id"],
    )
    assert (
        rehearsal._agent_model_was_substituted(model_catalog, config, fallback) is True
    )
