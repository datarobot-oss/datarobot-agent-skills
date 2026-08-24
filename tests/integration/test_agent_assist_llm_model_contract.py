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
from urllib.error import HTTPError

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
    header, _rule, row = list_llm_models.format_as_table(
        [_gateway_model()]
    ).splitlines()
    # Read the first column rather than searching the whole table: the llmId is a
    # substring of nothing here today, but that is an accident of this fixture.
    assert header.split("|")[0].strip() == "LLM_DEFAULT_MODEL"
    assert row.split("|")[0].strip() == CANONICAL


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
    """With credentials, the catalog is the authority on the exact spelling."""
    catalog([_gateway_model()])
    assert (
        setup_template.canonical_gateway_model(API_MODEL.upper(), tmp_path) == CANONICAL
    )


def test_catalog_overrules_the_slash_heuristic(tmp_path: Path, catalog: Any) -> None:
    """The no-slash rule is a fallback for when the catalog cannot be read. A
    catalog free to register a bare litellm name must not be second-guessed."""
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
    """A readable catalog does not excuse a no-slash llmId. It matches no api_model
    and is not a provider path, so it is refused rather than prefixed and written."""
    catalog([_gateway_model()])
    assert setup_template.canonical_gateway_model(LLM_ID, tmp_path) is None


def test_unreachable_catalog_does_not_block_setup(tmp_path: Path, catalog: Any) -> None:
    """An instance this process cannot reach must not stop a scaffold."""
    catalog(RuntimeError("connection refused"))
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) == CANONICAL


def test_connection_reset_does_not_block_setup(tmp_path: Path, catalog: Any) -> None:
    """urlopen lets raw OSError subclasses past the fetch helper's URLError
    handling, so catching RuntimeError alone let a reset kill the whole setup."""
    catalog(ConnectionResetError(54, "Connection reset by peer"))
    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) == CANONICAL


def test_empty_gateway_points_at_a_deployed_llm(
    tmp_path: Path, catalog: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """An on-prem instance with the gateway off must get a way forward, not a
    refusal followed by an empty list of alternatives."""
    catalog([])

    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) is None

    err = capsys.readouterr().err
    assert "--llm-deployment-id" in err
    assert "Available:" not in err


def test_disabled_gateway_is_treated_as_empty(
    tmp_path: Path, catalog: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 404 from the catalog endpoint is the instance answering that it has no
    gateway, not a failure to reach it. Passing it as unverified would hand back a
    model the instance cannot serve."""
    http_404 = HTTPError("https://x/api/v2/genai/llmgw/catalog/", 404, "", {}, None)  # type: ignore[arg-type]
    catalog(RuntimeError("Failed to fetch LLM Gateway catalog"), cause=http_404)

    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) is None
    assert "--llm-deployment-id" in capsys.readouterr().err


def test_forbidden_catalog_is_not_a_disabled_gateway(
    tmp_path: Path, catalog: Any
) -> None:
    """A 403 says this token may not read the catalog, not that the gateway is
    absent. Refusing on it sends a user to a deployed LLM they do not need."""
    forbidden = HTTPError("https://x/api/v2/genai/llmgw/catalog/", 403, "", {}, None)  # type: ignore[arg-type]
    catalog(RuntimeError("Failed to fetch LLM Gateway catalog"), cause=forbidden)

    assert setup_template.canonical_gateway_model(API_MODEL, tmp_path) == CANONICAL


def test_env_file_carries_the_canonical_value(tmp_path: Path) -> None:
    ok, _ = setup_template.create_env_file(tmp_path, CANONICAL)
    assert ok
    assert f'LLM_DEFAULT_MODEL="{CANONICAL}"' in (tmp_path / ".env").read_text()


def test_env_file_refuses_a_value_that_would_break_the_line(tmp_path: Path) -> None:
    """The value lands in a double-quoted line the template's loader re-parses, so
    a quote closes it early and the rest becomes further keys."""
    ok, _ = setup_template.create_env_file(tmp_path, 'a/b" \nFOO="bar')
    assert not ok
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize("bad_char", ['"', "\\", "$", " ", "\n", "`"])
def test_env_file_rejects_each_dangerous_character(
    tmp_path: Path, bad_char: str
) -> None:
    """Each break-out character is refused on its own, not only in the combined
    value above, so no single one can slip through the guard."""
    ok, _ = setup_template.create_env_file(tmp_path, f"datarobot/azure/gpt-5{bad_char}")
    assert not ok
    assert not (tmp_path / ".env").exists()


def test_env_file_rejects_an_empty_model(tmp_path: Path) -> None:
    """An empty LLM_DEFAULT_MODEL is not a usable value; the '+' guard rejects it."""
    ok, _ = setup_template.create_env_file(tmp_path, "")
    assert not ok
    assert not (tmp_path / ".env").exists()


def test_env_file_accepts_every_shape_the_real_catalog_uses(tmp_path: Path) -> None:
    """':' and '@' are load-bearing, so the guard cannot be tightened to [\\w/-]."""
    for model in (
        "datarobot/bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
        "datarobot/vertex_ai/claude-haiku-4-5@20251001",
        "datarobot/azure/gpt-5-2025-08-07",
        "datarobot/datarobot-deployed-llm",
    ):
        ok, msg = setup_template.create_env_file(tmp_path, model)
        assert ok, f"{model} rejected: {msg}"


# -- the docs the agent copies from ---------------------------------------------


# Every provider the LLM Gateway catalog routes through. An example naming
# anything else is addressing a provider that does not exist, which is how
# `google/gemini-2.5-pro-preview-05-06` shipped: the real entry is under
# `vertex_ai/`. Whether a given model is still listed cannot be checked without
# the network, so this is the shape check, not a membership check.
CATALOG_PROVIDERS = {"anthropic", "azure", "bedrock", "vertex_ai"}


def test_spec_examples_use_canonical_model_names() -> None:
    """The worked examples are what an agent imitates, so they have to be shaped
    like values setup_template.py accepts: prefixed, and naming a real provider."""
    examples = (SCRIPTS_DIR.parent / "references/agent-spec-examples.md").read_text()
    models = [
        line.split(":", 1)[1].strip().strip("\"'")
        for line in examples.splitlines()
        if line.startswith("model:")
    ]
    assert models, "no model: lines found in agent-spec-examples.md"
    for model in models:
        assert model.startswith("datarobot/"), f"{model} is missing the prefix"
        bare = list_llm_models.normalize_gateway_model(model)
        # A catalog model is a provider path. A bare name is an llmId.
        assert "/" in bare, model
        provider = bare.split("/", 1)[0]
        assert provider in CATALOG_PROVIDERS, f"{model} names no real provider"


# -- the rehearsal still resolves it --------------------------------------------


def _model_catalog(monkeypatch: pytest.MonkeyPatch, entries: list[Any]) -> Any:
    monkeypatch.setattr(rehearsal, "fetch_llm_models", lambda *_: entries)
    return rehearsal.ModelCatalog("token", "https://example.invalid/api/v2")


def test_rehearsal_resolves_the_canonical_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Writing the prefixed form must not cost an exact match in the rehearsal."""
    model_catalog = _model_catalog(monkeypatch, [_gateway_model()])

    resolved, substituted = model_catalog.pick_available(CANONICAL)

    assert substituted is False
    # Still the bare form on the wire, whatever spelling the spec carried.
    assert resolved.api_model == API_MODEL


def test_rehearsal_keeps_the_provider_guard_on_a_prefixed_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A near-miss spec falls through to slug matching, which reads a provider off
    the front of the request. Left unprefixed, every request reads as provider
    'datarobot', the cross-provider guard stops applying, and the rehearsal runs
    against whichever model happens to be first in the catalog."""
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

    # Dots where the catalog has dashes, so the exact match misses on purpose.
    resolved, substituted = model_catalog.pick_available(
        "datarobot/anthropic/claude-sonnet-4.5-20250929"
    )

    assert substituted is True
    assert resolved.api_model == "anthropic/claude-sonnet-4-5-20250929"
