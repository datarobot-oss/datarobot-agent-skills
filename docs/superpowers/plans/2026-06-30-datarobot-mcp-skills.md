# DataRobot MCP Tool Skills — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three composable skills — `datarobot-define-tool-schema`, `datarobot-register-mcp-tool`, `datarobot-deploy-nim` — that let a customer expose a DataRobot deployment (predictive, agent, or NVIDIA NIM) as an MCP tool via the platform-native path instead of hand-rolled glue.

**Architecture:** Each skill is a `skills/datarobot-<name>/` directory with a human-authored `SKILL.md` plus agent-built `scripts/` (Python, using the DataRobot SDK + REST escape hatches). The skills compose: `register-mcp-tool` calls `define-tool-schema` for custom I/O; `deploy-nim` calls `register-mcp-tool` to expose the deployed NIM. All three ship in the single existing plugin (one version bump).

**Tech Stack:** Python 3.13, `datarobot` SDK (3.16.x), `requests`/SDK `Client.post/put` for REST escape hatches, `pytest` for unit tests, the repo's `dr_agents_tester` LLM-judge e2e harness, `pyyaml` for `model-metadata.yaml`.

## Global Constraints

- Every skill folder MUST start with `datarobot-` (`tests/integration/test_skills.py`).
- `SKILL.md` frontmatter `name` MUST equal the folder name (`test_skills.py`).
- `SKILL.md` `description` MUST contain the literal substring `Use when` (`test_skills.py`).
- `SKILL.md` estimated tokens: warn > 3300, **error > 6700** — must stay under 6700 (`test_skills.py`).
- Every skill needs an explicit `.github/CODEOWNERS` entry that is NOT `@datarobot-oss/datarobot-agent-skills` (`tests/integration/test_codeowners.py`). All three → `@datarobot/core-modeling`.
- All `.py` files start with the two-line copyright header:
  `# Copyright (c) 2026 DataRobot, Inc. All rights reserved.` / `# SPDX-License-Identifier: Apache-2.0`.
- SDK client init pattern (copy verbatim): `dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"), endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))`.
- Interface envelope: only `path_params`, `query_params`, `data`, `json` top-level keys; `path_params`/`query_params` flat; `data` nested-with-string-primitives; `json` arbitrary; `$ref`/`$defs` allowed; empty rejected unless `MCP_SERVER_TOOL_REGISTRATION_ALLOW_EMPTY_SCHEMA=true`. Requires `datarobot-drum >= 1.17.2`.
- Deployment-as-tool selection = tag `tool` with value `tool`.
- Hosted MCP endpoint: `https://<host>/api/v2/genai/globalmcp/mcp`. Self-hosted: `https://<host>/deployments/<id>/directAccess/mcp/`.
- Feature flag `ENABLE_MCP_TOOLS_GALLERY_SUPPORT` (hosted only): readable via `POST /api/v2/entitlements/evaluate/`; NO public write.
- **SKILL.md is fully authored by the implementer** (complete prose, not a skeleton). The maintainer explicitly overrode `CLAUDE.md`'s human-written preference. Each SKILL.md must read as a finished, self-contained skill: real prose under every heading, concrete commands, and trigger phrases woven into the `description` and Quick Start. Stay under the 6700-token error threshold; aim under 3300.
- Version bump: `1.3.2` → `1.4.0` (minor: new skills) in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `gemini-extension.json`. Add `CHANGELOG.md` entries under `[Unreleased]`.
- **Two per-skill manifests must list every skill (both enforced by `task lint`):** (1) `gemini-extension.json` `skills` array — `{name, path: skills/<name>/SKILL.md, description}`; (2) `docs/.well-known/ai-catalog.json` `entries` array — `{identifier: "urn:ai:github.com:datarobot-oss:datarobot-agent-skills:<suffix-after-datarobot->", displayName: "<folder name>", type: "application/ai-skill", url: "https://github.com/datarobot-oss/datarobot-agent-skills/blob/main/skills/<name>/SKILL.md", description, representativeQueries: [3 trigger-phrase strings]}`. Both entries are added by the skill's SKILL.md task (alongside creating the SKILL.md), never before its SKILL.md exists.

---

## Phase 0 — Scaffolding

### Task 0: CODEOWNERS, version bump, changelog

**Files:**
- Modify: `.github/CODEOWNERS`, `.claude-plugin/plugin.json:4`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json:4`, `gemini-extension.json:3`, `CHANGELOG.md`
- Test: `tests/integration/test_codeowners.py`, `tests/integration/test_plugins.py` (existing)

**Interfaces:**
- Produces: CODEOWNERS + version + changelog groundwork. Does NOT create skill dirs.

> **Do NOT create the skill directories or add gemini-extension.json skill entries here.** `test_gemini_all_skills_included` requires every `skills/` dir to be listed in `gemini-extension.json`, and `test_gemini_entry_path_exists` requires each listed entry's `path` (`skills/<name>/SKILL.md`) to exist — so an empty skill dir breaks the suite. Each skill's dir is created by its first script task; its gemini-extension.json entry is added by its SKILL.md task (A2/B5/C4). CODEOWNERS entries for not-yet-existing dirs are harmless (`test_codeowners` only checks dirs that contain a `SKILL.md`).

- [ ] **Step 1: Add CODEOWNERS entries** under the core-modeling block in `.github/CODEOWNERS`:

```
/skills/datarobot-define-tool-schema/ @datarobot/core-modeling
/skills/datarobot-register-mcp-tool/ @datarobot/core-modeling
/skills/datarobot-deploy-nim/ @datarobot/core-modeling
```

- [ ] **Step 2: Bump version `1.3.2` → `1.4.0`** in all four manifest files (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `gemini-extension.json`). Do not touch the `skills` arrays.

- [ ] **Step 3: Add CHANGELOG entries** under `## [Unreleased]`:

```markdown
- `datarobot-define-tool-schema`: New skill — author and validate the `model-metadata.yaml inputSchema` that makes a custom deployment callable as an MCP tool.
- `datarobot-register-mcp-tool`: New skill — register an existing deployment as an MCP tool (tag, surface on hosted/self-hosted MCP, feature-flag check, verify, emit client config).
- `datarobot-deploy-nim`: New skill — deploy an NVIDIA NIM with a GPU resource bundle and expose it as an MCP tool.
```

- [ ] **Step 4: Run structural tests.** Run: `uv run pytest tests/integration/test_plugins.py tests/integration/test_codeowners.py -q -k "not validate"`. Expected: PASS (the `*_validate` tests need the gemini/claude CLIs and are environmental; exclude them). Version-consistency assertions pass; no new skill dirs exist yet.

- [ ] **Step 5: Commit.**

```bash
git add .github/CODEOWNERS .claude-plugin .cursor-plugin gemini-extension.json CHANGELOG.md
git commit -m "scaffold: add codeowners + v1.4.0 bump for three MCP tool skills"
```

---

## Phase A — `datarobot-define-tool-schema` (shared component)

This skill is pure validation logic — fully unit-testable, no API calls. Build it first so the others can rely on it.

### Task A1: Schema validator (`validate_tool_schema.py`)

**Files:**
- Create: `skills/datarobot-define-tool-schema/scripts/validate_tool_schema.py`
- Test: `skills/datarobot-define-tool-schema/scripts/test_validate_tool_schema.py`

**Interfaces:**
- Produces: `validate_tool_schema(schema: dict, allow_empty: bool = False) -> list[str]` — returns a list of human-readable error strings (empty list = valid). Mirrors `datarobot_genai/drmcpbase/dynamic_tools/schema.py` rules.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from validate_tool_schema import validate_tool_schema


def test_valid_json_body_schema_passes():
    schema = {"type": "object", "properties": {
        "json": {"type": "object", "properties": {"text": {"type": "string"}}}},
        "required": ["json"]}
    assert validate_tool_schema(schema) == []


def test_unknown_top_level_key_rejected():
    schema = {"type": "object", "properties": {"body": {"type": "object"}}}
    errors = validate_tool_schema(schema)
    assert any("body" in e and "not allowed" in e for e in errors)


def test_empty_schema_rejected_unless_allowed():
    schema = {"type": "object", "properties": {}}
    assert validate_tool_schema(schema, allow_empty=False) != []
    assert validate_tool_schema(schema, allow_empty=True) == []


def test_path_params_must_be_flat():
    schema = {"type": "object", "properties": {"path_params": {"type": "object",
        "properties": {"nested": {"type": "object"}}}}}
    errors = validate_tool_schema(schema)
    assert any("path_params" in e and "flat" in e for e in errors)


def test_query_params_must_be_flat():
    schema = {"type": "object", "properties": {"query_params": {"type": "object",
        "properties": {"nested": {"type": "array", "items": {"type": "object"}}}}}}
    errors = validate_tool_schema(schema)
    assert any("query_params" in e for e in errors)
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-define-tool-schema/scripts && uv run pytest test_validate_tool_schema.py -v`. Expected: FAIL (ImportError / module not found).

- [ ] **Step 3: Implement the validator.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate a model-metadata.yaml `inputSchema` against datarobot-genai's rules.

Usage:
    python validate_tool_schema.py path/to/model-metadata.yaml
    python validate_tool_schema.py path/to/model-metadata.yaml --allow-empty
    python validate_tool_schema.py --schema '{"type":"object",...}'
"""
import json
import sys

ALLOWED_KEYS = {"path_params", "query_params", "data", "json"}
FLAT_KEYS = {"path_params", "query_params"}


def _is_flat_object(prop: dict) -> bool:
    """A flat object: every property is a JSON primitive (no object/array)."""
    for sub in (prop.get("properties") or {}).values():
        if sub.get("type") in ("object", "array"):
            return False
    return True


def validate_tool_schema(schema: dict, allow_empty: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["schema must be a JSON object"]
    props = schema.get("properties") or {}
    if not props:
        if not allow_empty:
            errors.append(
                "schema has no properties; empty schemas are rejected unless "
                "MCP_SERVER_TOOL_REGISTRATION_ALLOW_EMPTY_SCHEMA=true"
            )
        return errors
    for key, prop in props.items():
        if key not in ALLOWED_KEYS:
            errors.append(
                f"top-level key '{key}' is not allowed; only {sorted(ALLOWED_KEYS)} are permitted"
            )
            continue
        if key in FLAT_KEYS and not _is_flat_object(prop):
            errors.append(
                f"'{key}' must be a flat object (primitive properties only, no nested object/array)"
            )
    return errors


def _load(path: str) -> dict:
    import yaml  # local import; only needed for the file path mode
    with open(path) as fh:
        meta = yaml.safe_load(fh)
    return meta.get("inputSchema", meta)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--allow-empty"]
    allow_empty = "--allow-empty" in argv
    if len(args) >= 2 and args[0] == "--schema":
        schema = json.loads(args[1])
    elif len(args) >= 1:
        schema = _load(args[0])
    else:
        print(__doc__)
        return 2
    errors = validate_tool_schema(schema, allow_empty=allow_empty)
    if errors:
        print("INVALID inputSchema:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("inputSchema is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-define-tool-schema/scripts && uv run pytest test_validate_tool_schema.py -v`. Expected: 5 passed.

- [ ] **Step 5: Lint + commit.** Run: `task lint` (fix any copyright/format issues), then:

```bash
git add skills/datarobot-define-tool-schema/scripts/
git commit -m "feat(define-tool-schema): add inputSchema validator with unit tests"
```

### Task A2: Author `SKILL.md` (full prose)

**Files:**
- Create: `skills/datarobot-define-tool-schema/SKILL.md`
- Test: `tests/integration/test_skills.py`, `tests/e2e/test_skills_e2e.py`

**Interfaces:**
- Consumes: `scripts/validate_tool_schema.py` (referenced in prose).

- [ ] **Step 1: Author the full SKILL.md.** Use this frontmatter and these sections, writing complete prose under every heading (the `<!-- -->` notes say what each section must cover — replace them with real content, don't leave comments in the file):

```markdown
---
name: datarobot-define-tool-schema
description: Author and validate the model-metadata.yaml inputSchema that makes a custom DataRobot deployment callable as an MCP tool. Use when a deployment exposes custom (non-chat, non-predictive) request/response shapes and needs a tool interface defined or fixed.
---

# DataRobot Define Tool Schema Skill

## Quick Start
<!-- maintainer: 3-step happy path referencing scripts/validate_tool_schema.py -->

## When to use this skill
<!-- maintainer: custom I/O only; predictive + chat/NIM use auto-fallbacks (point to register-mcp-tool) -->

## The interface envelope
<!-- maintainer: path_params/query_params/data/json; flatness rules; $ref/$defs; empty-schema flag; drum >= 1.17.2 -->

## Authoring an inputSchema
<!-- maintainer: worked example mapping a deployment's request to the envelope -->

## Validating
<!-- maintainer: `python scripts/validate_tool_schema.py model-metadata.yaml` -->

## Scripts
- `scripts/validate_tool_schema.py` — validate an inputSchema against datarobot-genai's rules
```

**Suggested trigger phrases** (for the maintainer to weave into `description`/Quick Start): "define the tool schema for my deployment", "my MCP tool has the wrong inputs", "write the inputSchema for model-metadata.yaml", "validate my deployment's tool interface".

- [ ] **Step 2: Add the gemini-extension.json entry.** Append to the `skills` array in `gemini-extension.json` (matching the format of existing entries — `name` = folder name, `path` = `skills/datarobot-define-tool-schema/SKILL.md`, plus the same `description`/keys siblings use). This is required: `test_gemini_all_skills_included` now sees the dir on disk.

- [ ] **Step 3: Verify structural + plugin tests pass.** Run: `uv run pytest tests/integration/test_skills.py tests/integration/test_plugins.py -k "define_tool_schema or all_skills_included" -v` and `... -k "not validate"` for the rest. Expected: name-matches-folder, description-has-"Use when", token-count, gemini-entry-path-exists, and all-skills-included all PASS. (The `*_validate` tests need external CLIs — skip them.)

- [ ] **Step 4: Commit.** `git add skills/datarobot-define-tool-schema/SKILL.md gemini-extension.json && git commit -m "docs(define-tool-schema): author SKILL.md + gemini entry"`.

---

## Phase B — `datarobot-register-mcp-tool` (headline skill, ships first)

### Task B1: Emit client config (`emit_client_config.py`)

**Files:**
- Create: `skills/datarobot-register-mcp-tool/scripts/emit_client_config.py`
- Test: `skills/datarobot-register-mcp-tool/scripts/test_emit_client_config.py`

**Interfaces:**
- Produces: `build_client_config(host: str, deployment_id: str | None, hosted: bool, client: str) -> dict` — returns the MCP client config object. `client` ∈ {"claude", "cursor"}.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from emit_client_config import build_client_config


def test_hosted_url_uses_globalmcp_path():
    cfg = build_client_config("https://app.datarobot.com", None, hosted=True, client="cursor")
    url = cfg["mcpServers"]["datarobot"]["url"]
    assert url == "https://app.datarobot.com/api/v2/genai/globalmcp/mcp"


def test_self_hosted_url_uses_directaccess_path():
    cfg = build_client_config("https://app.datarobot.com", "dep123", hosted=False, client="cursor")
    url = cfg["mcpServers"]["datarobot"]["url"]
    assert url == "https://app.datarobot.com/deployments/dep123/directAccess/mcp/"


def test_self_hosted_requires_deployment_id():
    import pytest
    with pytest.raises(ValueError):
        build_client_config("https://app.datarobot.com", None, hosted=False, client="cursor")


def test_auth_header_present():
    cfg = build_client_config("https://app.datarobot.com", None, hosted=True, client="cursor")
    headers = cfg["mcpServers"]["datarobot"]["headers"]
    assert headers["Authorization"] == "Bearer ${DATAROBOT_API_TOKEN}"
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_emit_client_config.py -v`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Emit MCP client config for connecting to a DataRobot MCP server.

Usage:
    python emit_client_config.py --host https://app.datarobot.com --hosted
    python emit_client_config.py --host https://app.datarobot.com --deployment-id dep123 --self-hosted
"""
import argparse
import json
import sys


def build_client_config(host: str, deployment_id: str | None, hosted: bool, client: str) -> dict:
    host = host.rstrip("/")
    if hosted:
        url = f"{host}/api/v2/genai/globalmcp/mcp"
    else:
        if not deployment_id:
            raise ValueError("self-hosted config requires a deployment_id")
        url = f"{host}/deployments/{deployment_id}/directAccess/mcp/"
    return {
        "mcpServers": {
            "datarobot": {
                "url": url,
                "headers": {"Authorization": "Bearer ${DATAROBOT_API_TOKEN}"},
            }
        }
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--deployment-id")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hosted", action="store_true")
    mode.add_argument("--self-hosted", dest="self_hosted", action="store_true")
    p.add_argument("--client", choices=["claude", "cursor"], default="cursor")
    args = p.parse_args(argv[1:])
    cfg = build_client_config(args.host, args.deployment_id, args.hosted, args.client)
    print(json.dumps(cfg, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_emit_client_config.py -v`. Expected: 4 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-register-mcp-tool/scripts/emit_client_config.py skills/datarobot-register-mcp-tool/scripts/test_emit_client_config.py && git commit -m "feat(register-mcp-tool): client config emitter"`.

### Task B2: Feature-flag check (`check_tool_gallery_flag.py`)

**Files:**
- Create: `skills/datarobot-register-mcp-tool/scripts/check_tool_gallery_flag.py`
- Test: `skills/datarobot-register-mcp-tool/scripts/test_check_tool_gallery_flag.py`

**Interfaces:**
- Produces: `is_tool_gallery_enabled(client) -> bool` where `client` is anything with `.post(url, data=...)` returning an object with `.json()`. Posts to `entitlements/evaluate/` for `ENABLE_MCP_TOOLS_GALLERY_SUPPORT`.

- [ ] **Step 1: Write failing tests** using a fake client (no network).

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from check_tool_gallery_flag import is_tool_gallery_enabled


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, value):
        self._value = value
        self.last = None

    def post(self, url, data=None, **kwargs):
        self.last = (url, data)
        return _Resp({"entitlements": [{"name": "ENABLE_MCP_TOOLS_GALLERY_SUPPORT",
                                        "value": self._value}]})


def test_returns_true_when_entitled():
    assert is_tool_gallery_enabled(_Client(True)) is True


def test_returns_false_when_not_entitled():
    assert is_tool_gallery_enabled(_Client(False)) is False


def test_posts_to_entitlements_evaluate():
    c = _Client(True)
    is_tool_gallery_enabled(c)
    url, data = c.last
    assert "entitlements/evaluate" in url
    assert "ENABLE_MCP_TOOLS_GALLERY_SUPPORT" in str(data)
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_check_tool_gallery_flag.py -v`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Check the hosted Global MCP tool-gallery feature flag.

The flag (`ENABLE_MCP_TOOLS_GALLERY_SUPPORT`) is read-only via the public API.
There is no public write — if disabled, an on-prem admin toggles it, or a cloud
customer requests it from DataRobot (ref PBMP-7644). Self-hosted MCP ignores it.

Usage:
    python check_tool_gallery_flag.py
"""
import json
import os
import sys

FLAG = "ENABLE_MCP_TOOLS_GALLERY_SUPPORT"


def is_tool_gallery_enabled(client) -> bool:
    resp = client.post(
        "entitlements/evaluate/",
        data=json.dumps({"entitlements": [{"name": FLAG}]}),
    )
    payload = resp.json()
    for ent in payload.get("entitlements", []):
        if ent.get("name") == FLAG:
            return bool(ent.get("value"))
    return False


def main(argv: list[str]) -> int:
    import datarobot as dr

    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )
    enabled = is_tool_gallery_enabled(client)
    if enabled:
        print(f"{FLAG}: ENABLED — tagged deployments will appear on the hosted MCP.")
        return 0
    print(
        f"{FLAG}: DISABLED.\n"
        "  - On-prem: an org admin can enable it in the admin console.\n"
        "  - Cloud: request enablement from DataRobot (ref PBMP-7644).\n"
        "  - Unblocked alternative: self-host the MCP server (it ignores this flag)."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_check_tool_gallery_flag.py -v`. Expected: 3 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-register-mcp-tool/scripts/check_tool_gallery_flag.py skills/datarobot-register-mcp-tool/scripts/test_check_tool_gallery_flag.py && git commit -m "feat(register-mcp-tool): tool-gallery feature-flag check"`.

### Task B3: Tag a deployment + self-hosted register (`register_deployment_tool.py`)

**Files:**
- Create: `skills/datarobot-register-mcp-tool/scripts/register_deployment_tool.py`
- Test: `skills/datarobot-register-mcp-tool/scripts/test_register_deployment_tool.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces:
  - `tag_as_tool(deployment) -> list[dict]` — returns the new tags list including `{"name": "tool", "value": "tool"}`, idempotent (no duplicate). `deployment` exposes `.tags` (list of `{name,value}`) and `.update(tags=...)`.
  - `self_hosted_register_url(mcp_base_url: str, deployment_id: str) -> str` — builds the `PUT /registeredDeployments/{id}` URL for a self-hosted server.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from register_deployment_tool import tag_as_tool, self_hosted_register_url


class _Deployment:
    def __init__(self, tags):
        self.tags = tags
        self.updated_with = None

    def update(self, tags=None):
        self.updated_with = tags


def test_tag_added_when_absent():
    dep = _Deployment(tags=[{"name": "env", "value": "prod"}])
    result = tag_as_tool(dep)
    assert {"name": "tool", "value": "tool"} in result
    assert dep.updated_with == result


def test_tag_not_duplicated_when_present():
    dep = _Deployment(tags=[{"name": "tool", "value": "tool"}])
    result = tag_as_tool(dep)
    assert result.count({"name": "tool", "value": "tool"}) == 1
    assert dep.updated_with is None  # no update needed


def test_self_hosted_register_url():
    url = self_hosted_register_url(
        "https://app.datarobot.com/deployments/dep1/directAccess/mcp/", "dep1")
    assert url == ("https://app.datarobot.com/deployments/dep1/directAccess/mcp/"
                   "registeredDeployments/dep1")
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_register_deployment_tool.py -v`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tag a deployment as an MCP tool, and (self-hosted) register it at runtime.

Hosted Global MCP: tagging is enough; the client must reconnect to see the tool.
Self-hosted MCP: tag, then PUT /registeredDeployments/{id} (no restart) OR restart
with MCP_SERVER_REGISTER_DYNAMIC_TOOLS_ON_STARTUP=true.

Usage:
    python register_deployment_tool.py <deployment_id>
    python register_deployment_tool.py <deployment_id> --self-hosted-mcp-url <url>
"""
import argparse
import os
import sys

TOOL_TAG = {"name": "tool", "value": "tool"}


def tag_as_tool(deployment) -> list[dict]:
    tags = list(deployment.tags or [])
    if TOOL_TAG in tags:
        return tags
    tags.append(TOOL_TAG)
    deployment.update(tags=tags)
    return tags


def self_hosted_register_url(mcp_base_url: str, deployment_id: str) -> str:
    base = mcp_base_url if mcp_base_url.endswith("/") else mcp_base_url + "/"
    return f"{base}registeredDeployments/{deployment_id}"


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("deployment_id")
    p.add_argument("--self-hosted-mcp-url", dest="self_hosted_mcp_url")
    args = p.parse_args(argv[1:])

    dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )
    deployment = dr.Deployment.get(args.deployment_id)
    tag_as_tool(deployment)
    print(f"Tagged deployment {args.deployment_id} with tool=tool.")

    if args.self_hosted_mcp_url:
        import requests

        url = self_hosted_register_url(args.self_hosted_mcp_url, args.deployment_id)
        resp = requests.put(
            url,
            headers={"Authorization": f"Bearer {os.getenv('DATAROBOT_API_TOKEN')}"},
            timeout=30,
        )
        resp.raise_for_status()
        print(f"Registered with self-hosted MCP at {url} (status {resp.status_code}).")
    else:
        print("Hosted MCP: reconnect your client to pick up the new tool.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_register_deployment_tool.py -v`. Expected: 3 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-register-mcp-tool/scripts/register_deployment_tool.py skills/datarobot-register-mcp-tool/scripts/test_register_deployment_tool.py && git commit -m "feat(register-mcp-tool): tag + self-hosted runtime register"`.

### Task B4: Verify the tool appears (`verify_mcp_tool.py`)

**Files:**
- Create: `skills/datarobot-register-mcp-tool/scripts/verify_mcp_tool.py`
- Test: `skills/datarobot-register-mcp-tool/scripts/test_verify_mcp_tool.py`

**Interfaces:**
- Produces: `tool_name_for_deployment(deployment_id: str, tools: list[dict]) -> str | None` — find the tool whose metadata maps to the deployment; `assert_tool_present(deployment_id, tools) -> bool`. The live `tools/list` call is isolated behind `list_tools(mcp_url, token)` so the pure matching logic is unit-tested without network.

> **Live-API note for the implementer:** the exact MCP client call and how a tool's `meta`/name ties back to a `deployment_id` must be confirmed against `datarobot-genai` (`_create_tool_from_custom_model_deployment` sets `meta={"tool_category": "USER_TOOL_DEPLOYMENT"}` and a derived `name`). Implement `list_tools()` with the `mcp`/`fastmcp` streamable-HTTP client and confirm the name/meta shape against a live deployment in Task B6. Do NOT guess the field — verify it.

- [ ] **Step 1: Write failing tests** for the pure matching logic.

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from verify_mcp_tool import tool_name_for_deployment, assert_tool_present


def _tools():
    return [
        {"name": "weather", "meta": {"deployment_id": "depA"}},
        {"name": "scorer", "meta": {"deployment_id": "depB"}},
    ]


def test_finds_tool_by_deployment_id():
    assert tool_name_for_deployment("depB", _tools()) == "scorer"


def test_returns_none_when_absent():
    assert tool_name_for_deployment("depZ", _tools()) is None


def test_assert_present_true_false():
    assert assert_tool_present("depA", _tools()) is True
    assert assert_tool_present("depZ", _tools()) is False
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_verify_mcp_tool.py -v`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement the matching logic + a thin live wrapper.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify a tagged deployment shows up as an MCP tool.

Usage:
    python verify_mcp_tool.py <deployment_id> --mcp-url <url>
"""
import argparse
import os
import sys


def tool_name_for_deployment(deployment_id: str, tools: list[dict]) -> str | None:
    for tool in tools:
        meta = tool.get("meta") or {}
        if meta.get("deployment_id") == deployment_id:
            return tool.get("name")
    return None


def assert_tool_present(deployment_id: str, tools: list[dict]) -> bool:
    return tool_name_for_deployment(deployment_id, tools) is not None


def list_tools(mcp_url: str, token: str) -> list[dict]:
    """Connect to the MCP server and return the tools/list payload as dicts.

    IMPLEMENTER: build with the streamable-HTTP MCP client and confirm the
    tool name/meta shape against a live deployment (see Task B6). The metadata
    key that carries the deployment id MUST be verified, not assumed.
    """
    raise NotImplementedError("wire up the MCP streamable-HTTP client; verify in B6")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("deployment_id")
    p.add_argument("--mcp-url", required=True)
    args = p.parse_args(argv[1:])
    tools = list_tools(args.mcp_url, os.getenv("DATAROBOT_API_TOKEN"))
    name = tool_name_for_deployment(args.deployment_id, tools)
    if name:
        print(f"OK: deployment {args.deployment_id} is exposed as tool '{name}'.")
        return 0
    print(f"NOT FOUND: deployment {args.deployment_id} is not in tools/list. "
          "Hosted: reconnect client + check the feature flag. Self-hosted: register/restart.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_verify_mcp_tool.py -v`. Expected: 3 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-register-mcp-tool/scripts/verify_mcp_tool.py skills/datarobot-register-mcp-tool/scripts/test_verify_mcp_tool.py && git commit -m "feat(register-mcp-tool): tool-presence verification (matching logic + live wrapper)"`.

### Task B5: Author `SKILL.md` (full prose)

**Files:**
- Create: `skills/datarobot-register-mcp-tool/SKILL.md`
- Test: `tests/integration/test_skills.py`, `tests/e2e/test_skills_e2e.py`

- [ ] **Step 1: Author the full SKILL.md** (complete prose under every heading; replace the `<!-- -->` notes with real content, don't leave comments in the file).

```markdown
---
name: datarobot-register-mcp-tool
description: Register an existing DataRobot deployment (predictive, agent, or NIM) as an MCP tool so assistants call it natively instead of writing custom glue. Use when someone wants to use a DataRobot deployment as a tool in Claude/Cursor, expose a deployment to an MCP client, or asks why a tagged deployment isn't showing up.
---

# DataRobot Register MCP Tool Skill

## Quick Start
<!-- maintainer: tag -> (hosted: reconnect | self-hosted: register) -> verify -> client config -->

## Hosted Global MCP vs self-hosted user MCP
<!-- maintainer: endpoints, surfacing difference, when to choose which -->

## Deployment types
<!-- maintainer: predictive/agent/chat-NIM use auto-fallbacks; custom I/O -> use datarobot-define-tool-schema -->

## After tagging: making the tool appear
<!-- maintainer: hosted = reconnect client; self-hosted = PUT /registeredDeployments/{id} or restart -->

## Feature flag (hosted only)
<!-- maintainer: ENABLE_MCP_TOOLS_GALLERY_SUPPORT; read-only; enablement paths; self-host alternative -->

## Verify + connect your client
<!-- maintainer: verify_mcp_tool.py, then emit_client_config.py -->

## Scripts
- `scripts/register_deployment_tool.py` — tag tool=tool (+ self-hosted runtime register)
- `scripts/check_tool_gallery_flag.py` — read the hosted feature flag
- `scripts/verify_mcp_tool.py` — confirm the tool is in tools/list
- `scripts/emit_client_config.py` — produce Claude/Cursor MCP config
```

**Suggested trigger phrases:** "use my DataRobot deployment as a tool in Claude", "expose this deployment to Cursor over MCP", "register deployment X as an MCP tool", "I tagged my deployment but it's not showing up as a tool", "connect DataRobot MCP to my assistant".

- [ ] **Step 2: Add the gemini-extension.json entry** for `datarobot-register-mcp-tool` (`path` = `skills/datarobot-register-mcp-tool/SKILL.md`), matching the format of existing entries. **Also add the `docs/.well-known/ai-catalog.json` entry** (`identifier` urn suffix `register-mcp-tool`, `displayName` `datarobot-register-mcp-tool`, `url` the github blob to its SKILL.md, `description`, and 3 `representativeQueries` drawn from the trigger phrases) — matching the shape of existing catalog entries.

- [ ] **Step 3: Verify structural + plugin + catalog tests.** Run: `uv run pytest tests/integration/test_skills.py tests/integration/test_plugins.py tests/integration/test_catalog.py -k "register-mcp-tool or all_skills_included or catalog" -v` (pytest IDs use hyphens). Expected: PASS. (Skip the `*_validate` CLI tests.)

- [ ] **Step 4: Commit.** `git add skills/datarobot-register-mcp-tool/SKILL.md gemini-extension.json docs/.well-known/ai-catalog.json && git commit -m "docs(register-mcp-tool): author SKILL.md + gemini + catalog entries"`.

### Task B6: Correct verify matching + live e2e test

> **Correlation correction (source-grounded, from `datarobot-genai`):** B4's `verify_mcp_tool.py` matched on `meta.deployment_id`, which is WRONG. The real `tools/list` shape (verified in `global_mcp/providers/custom_model_tool_provider.py` + `dynamic_tools/deployment/config.py`):
> - Tool **`name`** = the **slugified deployment label** via `_convert_tool_string`: strip `[...]`, replace spaces/hyphens with `_`, drop non-`[A-Za-z0-9_]`, lowercase, collapse repeated `_`, trim `_`. Precedence: `deployment.label` → metadata name → fallback `deployment_<id>`.
> - **`title`** = the raw `deployment.label`.
> - **`meta`** = exactly `{"tool_category": "USER_TOOL_DEPLOYMENT"}` — **no deployment id**.
> - `annotations.deployment_id` is set in code but **not guaranteed** on the wire.
> So a verifier must match by **slugified label** (scoped to `meta.tool_category == "USER_TOOL_DEPLOYMENT"`), with `title == label` and `annotations.deployment_id == id` as corroborating signals.

**Files:**
- Rewrite: `skills/datarobot-register-mcp-tool/scripts/verify_mcp_tool.py` (+ its test) — corrected matching + live `list_tools`.
- Create: `tests/e2e/test_register_mcp_tool_live.py`
- Modify: `pyproject.toml` (add `fastmcp` + `httpx` to the `e2e` dependency group), `.env.example` (`E2E_TEST_DEPLOYMENT_ID`).

**Interfaces:**
- Produces:
  - `slugify_tool_name(label: str) -> str` — mirrors `_convert_tool_string`.
  - `expected_tool_name(label: str | None, deployment_id: str, metadata_name: str | None = None) -> str`.
  - `find_deployment_tool(tools: list[dict], label: str | None, deployment_id: str, metadata_name: str | None = None) -> dict | None`.
  - `assert_tool_present(tools, label, deployment_id, metadata_name=None) -> bool`.
  - `list_tools(mcp_url: str, token: str) -> list[dict]` — live `tools/list` via `fastmcp.Client`; each dict has `name`, `title`, `meta`, `annotations`.

- [ ] **Step 1: Rewrite the unit tests** (`test_verify_mcp_tool.py`) for the corrected matching.

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from verify_mcp_tool import (
    slugify_tool_name, expected_tool_name, find_deployment_tool, assert_tool_present,
)

CAT = {"tool_category": "USER_TOOL_DEPLOYMENT"}


def test_slugify_matches_convert_tool_string_rules():
    assert slugify_tool_name("My NIM [prod]") == "my_nim"
    assert slugify_tool_name("Sales-Predictor v2") == "sales_predictor_v2"


def test_expected_name_prefers_label_then_fallback():
    assert expected_tool_name("My NIM [prod]", "dep1") == "my_nim"
    assert expected_tool_name(None, "dep1") == "deployment_dep1"


def test_find_matches_by_slugified_label_scoped_to_category():
    tools = [
        {"name": "other", "title": "x", "meta": {"tool_category": "BUILTIN"}},
        {"name": "my_nim", "title": "My NIM [prod]", "meta": CAT, "annotations": {}},
    ]
    assert find_deployment_tool(tools, "My NIM [prod]", "dep1")["name"] == "my_nim"


def test_find_ignores_name_match_outside_deployment_category():
    tools = [{"name": "my_nim", "title": "My NIM", "meta": {"tool_category": "BUILTIN"}}]
    assert find_deployment_tool(tools, "My NIM", "dep1") is None


def test_find_matches_by_title_when_name_differs():
    tools = [{"name": "renamed", "title": "My NIM", "meta": CAT, "annotations": {}}]
    assert find_deployment_tool(tools, "My NIM", "dep1")["name"] == "renamed"


def test_find_matches_by_annotation_deployment_id_when_present():
    tools = [{"name": "z", "title": "z", "meta": CAT, "annotations": {"deployment_id": "dep1"}}]
    assert find_deployment_tool(tools, "unrelated label", "dep1")["name"] == "z"


def test_assert_present_false_when_absent():
    tools = [{"name": "a", "title": "a", "meta": CAT, "annotations": {}}]
    assert assert_tool_present(tools, "My NIM", "depX") is False
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_verify_mcp_tool.py -v`. Expected: FAIL (new functions not defined / old API).

- [ ] **Step 3: Rewrite `verify_mcp_tool.py`.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify a tagged deployment shows up as an MCP tool.

The MCP server names a deployment-tool after the SLUGIFIED deployment label
(datarobot-genai's `_convert_tool_string`), not the deployment id. `meta` only
carries `{"tool_category": "USER_TOOL_DEPLOYMENT"}`; the id may appear on
`annotations.deployment_id` but is not guaranteed on the wire. We match by
slugified label, scoped to that tool_category, with title/annotation corroboration.

Usage:
    python verify_mcp_tool.py <deployment_id> --mcp-url <url>
"""
import argparse
import os
import re
import sys

DEPLOYMENT_TOOL_CATEGORY = "USER_TOOL_DEPLOYMENT"


def slugify_tool_name(label: str) -> str:
    s = re.sub(r"\[.*?\]", "", label or "")
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_]", "", s)
    s = s.lower()
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def expected_tool_name(label, deployment_id: str, metadata_name=None) -> str:
    base = label or metadata_name or f"deployment_{deployment_id}"
    return slugify_tool_name(base) or f"deployment_{deployment_id}"


def find_deployment_tool(tools, label, deployment_id: str, metadata_name=None):
    want = expected_tool_name(label, deployment_id, metadata_name)
    for tool in tools:
        meta = tool.get("meta") or {}
        if meta.get("tool_category") != DEPLOYMENT_TOOL_CATEGORY:
            continue
        ann = tool.get("annotations") or {}
        if (
            tool.get("name") == want
            or (label and tool.get("title") == label)
            or ann.get("deployment_id") == deployment_id
        ):
            return tool
    return None


def assert_tool_present(tools, label, deployment_id: str, metadata_name=None) -> bool:
    return find_deployment_tool(tools, label, deployment_id, metadata_name) is not None


def list_tools(mcp_url: str, token: str) -> list[dict]:
    """Connect to the MCP server (streamable-HTTP) and return tools as dicts.

    Uses fastmcp's high-level client. NOTE: confirm the installed fastmcp's
    Client/transport API; this targets fastmcp>=2. Only invoked by the live
    e2e test (skipped unless creds are set), so it is not unit-tested here.
    """
    import asyncio

    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    async def _run():
        transport = StreamableHttpTransport(
            mcp_url, headers={"Authorization": f"Bearer {token}"}
        )
        async with Client(transport) as client:
            out = []
            for t in await client.list_tools():
                ann = getattr(t, "annotations", None)
                ann_d = (
                    ann.model_dump() if hasattr(ann, "model_dump")
                    else (dict(ann) if isinstance(ann, dict) else {})
                )
                out.append({
                    "name": t.name,
                    "title": getattr(t, "title", None),
                    "meta": getattr(t, "meta", None) or {},
                    "annotations": ann_d or {},
                })
            return out

    return asyncio.run(_run())


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("deployment_id")
    p.add_argument("--mcp-url", required=True)
    args = p.parse_args(argv[1:])

    dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
              endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))
    deployment = dr.Deployment.get(args.deployment_id)
    label = getattr(deployment, "label", None)
    tools = list_tools(args.mcp_url, os.getenv("DATAROBOT_API_TOKEN"))
    tool = find_deployment_tool(tools, label, args.deployment_id)
    if tool:
        print(f"OK: deployment {args.deployment_id} is exposed as tool '{tool['name']}'.")
        return 0
    print(f"NOT FOUND: deployment {args.deployment_id} is not in tools/list. "
          "Hosted: reconnect client + check the feature flag. Self-hosted: register/restart.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-register-mcp-tool/scripts && uv run pytest test_verify_mcp_tool.py -v`. Expected: 7 passed.

- [ ] **Step 5: Add `fastmcp` + `httpx` to the `e2e` dependency group** in `pyproject.toml` so the live test can import the client. The `e2e` group becomes:

```toml
e2e = [
    "datarobot-agent-tester @ git+https://github.com/datarobot/datarobot-agent-tester@main",
    "python-dotenv>=1.2.2",
    "pytest",
    "pytest-asyncio",
    "fastmcp>=2",
    "httpx>=0.27",
]
```

- [ ] **Step 6: Write the gated live e2e test** (`tests/e2e/test_register_mcp_tool_live.py`).

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Live e2e: tag a real deployment and confirm it surfaces as an MCP tool."""
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/datarobot-register-mcp-tool/scripts"
sys.path.insert(0, str(SCRIPTS))

REQUIRED = ["DATAROBOT_ENDPOINT", "DATAROBOT_API_TOKEN", "E2E_TEST_DEPLOYMENT_ID"]
pytestmark = pytest.mark.skipif(
    any(not os.getenv(v) for v in REQUIRED),
    reason=f"set {REQUIRED} to run the live MCP registration test",
)


def test_tag_and_surface_real_deployment():
    import datarobot as dr
    from register_deployment_tool import tag_as_tool
    from verify_mcp_tool import list_tools, assert_tool_present

    dep_id = os.environ["E2E_TEST_DEPLOYMENT_ID"]
    dr.Client(token=os.environ["DATAROBOT_API_TOKEN"],
              endpoint=os.environ["DATAROBOT_ENDPOINT"])
    deployment = dr.Deployment.get(dep_id)
    tag_as_tool(deployment)

    mcp_url = os.environ["DATAROBOT_ENDPOINT"].rstrip("/") + "/genai/globalmcp/mcp"
    tools = list_tools(mcp_url, os.environ["DATAROBOT_API_TOKEN"])
    assert assert_tool_present(tools, getattr(deployment, "label", None), dep_id), (
        "deployment tagged but not present in tools/list — "
        "check ENABLE_MCP_TOOLS_GALLERY_SUPPORT and client/list caching"
    )
```

- [ ] **Step 7: Add `E2E_TEST_DEPLOYMENT_ID`** to `.env.example` with a one-line comment.

- [ ] **Step 8: Confirm the live test skips cleanly without env.** Run: `uv run --group e2e pytest tests/e2e/test_register_mcp_tool_live.py -v`. Expected: SKIPPED (1 skipped). (A real run against a deployment requires the three env vars; capture that separately if creds are available.)

- [ ] **Step 9: Run `task lint`** from the repo root; confirm it passes (ruff/format on the rewritten script; integration suite still green). Commit: `git add skills/datarobot-register-mcp-tool/scripts/verify_mcp_tool.py skills/datarobot-register-mcp-tool/scripts/test_verify_mcp_tool.py tests/e2e/test_register_mcp_tool_live.py pyproject.toml .env.example && git commit -m "fix+test(register-mcp-tool): correct tool-name correlation + live e2e"`.

**MILESTONE: skills #3 and #1 are shippable here.** Run `task lint && uv run pytest tests/integration -q` before opening the PR.

---

## Phase C — `datarobot-deploy-nim`

> **Reality (corrected by research):** the NIM+GPU create→deploy flow is **fully REST-scriptable** — the earlier "UI-only" belief was wrong. The exact contract is in `docs/superpowers/research/nim-rest-contract.md` (grounded in the DataRobot API route handlers). None of these calls are in the public SDK, so scripts use the `dr.Client().get/post(...)` REST escape hatch. Genuine prerequisites (not automatable, surfaced by the skill): feature flags `NIM_MODELS` + `MLOPS_RESOURCE_REQUEST_BUNDLES`, and an NGC API key stored as a secureConfig (`secretConfigId`).

### Task C1: Discover NIM templates + GPU bundles (`discover_nim_options.py`)

**Files:**
- Create: `skills/datarobot-deploy-nim/scripts/discover_nim_options.py`
- Test: `skills/datarobot-deploy-nim/scripts/test_discover_nim_options.py`

**Interfaces:**
- Produces:
  - `filter_gpu_bundles(bundles: list) -> list` — keep only `has_gpu`, sorted by `gpu_count` then `gpu_memory_bytes`. Items expose `.has_gpu`, `.gpu_count`, `.gpu_memory_bytes`, `.id`, `.name`.
  - `pick_nim_template(templates: list[dict], name_substr: str | None = None) -> dict | None` — return the template whose `name` contains `name_substr` (case-insensitive); if `name_substr` is None, return the first template; None if the list is empty.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from discover_nim_options import filter_gpu_bundles, pick_nim_template


class _B:
    def __init__(self, id, has_gpu, gpu_count=0, gpu_memory_bytes=0):
        self.id, self.name = id, id
        self.has_gpu = has_gpu
        self.gpu_count = gpu_count
        self.gpu_memory_bytes = gpu_memory_bytes


def test_filters_non_gpu_and_sorts():
    out = filter_gpu_bundles([
        _B("cpu", False), _B("g2", True, 2, 10),
        _B("g1a", True, 1, 80), _B("g1b", True, 1, 40)])
    assert [b.id for b in out] == ["g1b", "g1a", "g2"]


def test_pick_template_by_substring():
    tpls = [{"id": "t1", "name": "Llama 3 NIM"}, {"id": "t2", "name": "Mixtral NIM"}]
    assert pick_nim_template(tpls, "mixtral")["id"] == "t2"


def test_pick_template_defaults_to_first():
    tpls = [{"id": "t1", "name": "A"}, {"id": "t2", "name": "B"}]
    assert pick_nim_template(tpls)["id"] == "t1"


def test_pick_template_empty_returns_none():
    assert pick_nim_template([], "x") is None
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_discover_nim_options.py -v`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Discover NIM templates and GPU resource bundles.

Lists NIM container templates (GET /customTemplates/?templateSubType=NIM_CONTAINERS)
and GPU resource bundles (ResourceBundle.list(use_cases=["customModel"])).

Usage:
    python discover_nim_options.py [--name <template name substring>]
"""
import argparse
import os
import sys


def filter_gpu_bundles(bundles: list) -> list:
    gpu = [b for b in bundles if getattr(b, "has_gpu", False)]
    return sorted(gpu, key=lambda b: (b.gpu_count, b.gpu_memory_bytes))


def pick_nim_template(templates: list[dict], name_substr: str | None = None) -> dict | None:
    if not templates:
        return None
    if name_substr is None:
        return templates[0]
    needle = name_substr.lower()
    for t in templates:
        if needle in (t.get("name") or "").lower():
            return t
    return None


def main(argv: list[str]) -> int:
    import datarobot as dr
    from datarobot.models.resource_bundle import ResourceBundle

    p = argparse.ArgumentParser()
    p.add_argument("--name", help="filter NIM template by name substring")
    args = p.parse_args(argv[1:])

    client = dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
                       endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))
    resp = client.get("customTemplates/", params={"templateSubType": "NIM_CONTAINERS"})
    templates = resp.json().get("data", [])
    chosen = pick_nim_template(templates, args.name)
    print("NIM templates:")
    for t in templates:
        marker = " <- chosen" if chosen and t.get("id") == chosen.get("id") else ""
        print(f"  {t.get('id')}\t{t.get('name')}{marker}")

    print("GPU resource bundles (use with --resource-bundle-id):")
    for b in filter_gpu_bundles(ResourceBundle.list(use_cases=["customModel"])):
        print(f"  {b.id}\t{b.name}\tgpu_count={b.gpu_count}\tgpu_mem={b.gpu_memory_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_discover_nim_options.py -v`. Expected: 4 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-deploy-nim/scripts/discover_nim_options.py skills/datarobot-deploy-nim/scripts/test_discover_nim_options.py && git commit -m "feat(deploy-nim): discover NIM templates + GPU bundles"`.

### Task C2: Create the NIM model from a template (`create_nim_from_template.py`)

**Files:**
- Create: `skills/datarobot-deploy-nim/scripts/create_nim_from_template.py`
- Test: `skills/datarobot-deploy-nim/scripts/test_create_nim_from_template.py`

**Interfaces:**
- Consumes: a `template_id` + `resource_bundle_id` from C1's discovery.
- Produces: `build_nim_create_payload(template_id, resource_bundle_id, secret_config_id=None, container_tag_override=None) -> dict` — body for `POST /customModels/fromModelTemplate/`. `templateId` and `resourceBundleId` always present; optional keys omitted when None.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from create_nim_from_template import build_nim_create_payload


def test_minimal_payload():
    body = build_nim_create_payload("tpl1", "bundleG")
    assert body == {"templateId": "tpl1", "resourceBundleId": "bundleG"}


def test_optional_fields_included_when_set():
    body = build_nim_create_payload("tpl1", "bundleG",
                                    secret_config_id="sec1", container_tag_override="latest")
    assert body["secretConfigId"] == "sec1"
    assert body["nimContainerTagOverride"] == "latest"


def test_requires_template_and_bundle():
    with pytest.raises(ValueError):
        build_nim_create_payload("", "bundleG")
    with pytest.raises(ValueError):
        build_nim_create_payload("tpl1", "")
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_create_nim_from_template.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Create a NIM custom model + version from a NIM container template.

REST: POST /api/v2/customModels/fromModelTemplate/  (requires feature flag NIM_MODELS).
Returns {"customModelId": ..., "customModelVersionId": ...}. The NGC API key must
already be stored as a secureConfig and passed as secret_config_id.

Usage:
    python create_nim_from_template.py --template-id <id> --resource-bundle-id <id> \
        [--secret-config-id <id>] [--container-tag-override <tag>]
"""
import argparse
import os
import sys


def build_nim_create_payload(template_id, resource_bundle_id,
                             secret_config_id=None, container_tag_override=None) -> dict:
    if not template_id or not resource_bundle_id:
        raise ValueError("template_id and resource_bundle_id are required")
    body = {"templateId": template_id, "resourceBundleId": resource_bundle_id}
    if secret_config_id:
        body["secretConfigId"] = secret_config_id
    if container_tag_override:
        body["nimContainerTagOverride"] = container_tag_override
    return body


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("--template-id", required=True)
    p.add_argument("--resource-bundle-id", required=True)
    p.add_argument("--secret-config-id")
    p.add_argument("--container-tag-override")
    args = p.parse_args(argv[1:])

    client = dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
                       endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))
    body = build_nim_create_payload(args.template_id, args.resource_bundle_id,
                                    args.secret_config_id, args.container_tag_override)
    resp = client.post("customModels/fromModelTemplate/", data=body)
    out = resp.json()
    print(f"customModelId={out.get('customModelId')} "
          f"customModelVersionId={out.get('customModelVersionId')}")
    print("Next: register + deploy with deploy_nim.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_create_nim_from_template.py -v`. Expected: 3 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-deploy-nim/scripts/create_nim_from_template.py skills/datarobot-deploy-nim/scripts/test_create_nim_from_template.py && git commit -m "feat(deploy-nim): create NIM model from template via REST"`.

### Task C3: Register + deploy the NIM (`deploy_nim.py`)

**Files:**
- Create: `skills/datarobot-deploy-nim/scripts/deploy_nim.py`
- Test: `skills/datarobot-deploy-nim/scripts/test_deploy_nim.py`

**Interfaces:**
- Consumes: a `custom_model_version_id` from C2.
- Produces:
  - `pick_serverless_pe(pes: list[dict]) -> dict | None` — choose the serverless PE: prefer `platform == "datarobot"` (case-insensitive), else the one whose `name` contains "serverless"; None if list empty.
  - `build_deploy_payload(model_package_id: str, label: str, prediction_environment_id: str) -> dict` — body for `POST /deployments/fromModelPackage/`; raises `ValueError` if `prediction_environment_id` is missing; never includes `defaultPredictionServerId`.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from deploy_nim import pick_serverless_pe, build_deploy_payload


def test_pick_serverless_prefers_datarobot_platform():
    pes = [{"id": "pe1", "platform": "aws", "name": "ext"},
           {"id": "pe2", "platform": "datarobot", "name": "Serverless"}]
    assert pick_serverless_pe(pes)["id"] == "pe2"


def test_pick_serverless_falls_back_to_name():
    pes = [{"id": "pe1", "platform": "aws", "name": "my serverless env"}]
    assert pick_serverless_pe(pes)["id"] == "pe1"


def test_pick_serverless_empty_none():
    assert pick_serverless_pe([]) is None


def test_deploy_payload_shape_and_pe_required():
    body = build_deploy_payload("pkg1", "my-nim", "pe2")
    assert body == {"modelPackageId": "pkg1", "label": "my-nim",
                    "predictionEnvironmentId": "pe2"}
    assert "defaultPredictionServerId" not in body
    with pytest.raises(ValueError):
        build_deploy_payload("pkg1", "my-nim", "")
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_deploy_nim.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Register a NIM custom model version and deploy it to a serverless GPU PE.

REST:
  POST /api/v2/modelPackages/fromCustomModelVersion/  {customModelVersionId, name}
  GET  /api/v2/predictionEnvironments/                 (pick the serverless PE)
  POST /api/v2/deployments/fromModelPackage/           {modelPackageId, label, predictionEnvironmentId}

Usage:
    python deploy_nim.py --custom-model-version-id <id> --label <name> \
        [--prediction-environment-id <id>]
"""
import argparse
import os
import sys


def pick_serverless_pe(pes: list[dict]) -> dict | None:
    if not pes:
        return None
    for pe in pes:
        if (pe.get("platform") or "").lower() == "datarobot":
            return pe
    for pe in pes:
        if "serverless" in (pe.get("name") or "").lower():
            return pe
    return None


def build_deploy_payload(model_package_id: str, label: str,
                         prediction_environment_id: str) -> dict:
    if not prediction_environment_id:
        raise ValueError("a serverless GPU prediction_environment_id is required")
    return {"modelPackageId": model_package_id, "label": label,
            "predictionEnvironmentId": prediction_environment_id}


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("--custom-model-version-id", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--prediction-environment-id")
    args = p.parse_args(argv[1:])

    client = dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
                       endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))

    pkg = client.post("modelPackages/fromCustomModelVersion/",
                      data={"customModelVersionId": args.custom_model_version_id,
                            "name": args.label}).json()
    model_package_id = pkg["id"]

    pe_id = args.prediction_environment_id
    if not pe_id:
        pes = client.get("predictionEnvironments/").json().get("data", [])
        chosen = pick_serverless_pe(pes)
        if not chosen:
            print("No serverless prediction environment found; pass --prediction-environment-id.")
            return 1
        pe_id = chosen["id"]

    body = build_deploy_payload(model_package_id, args.label, pe_id)
    resp = client.post("deployments/fromModelPackage/", data=body)
    out = resp.json()
    print(f"Deployment created: {out.get('id')} (status {resp.status_code}).")
    print("Next: expose it with datarobot-register-mcp-tool (NIM auto-detects as chat).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_deploy_nim.py -v`. Expected: 4 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-deploy-nim/scripts/deploy_nim.py skills/datarobot-deploy-nim/scripts/test_deploy_nim.py && git commit -m "feat(deploy-nim): register + deploy NIM to serverless GPU PE"`.

### Task C4: Author `SKILL.md` (full prose)

**Files:**
- Create: `skills/datarobot-deploy-nim/SKILL.md`
- Modify: `gemini-extension.json`
- Test: `tests/integration/test_skills.py`, `tests/integration/test_plugins.py`

- [ ] **Step 1: Author the full SKILL.md** (complete prose under every heading; replace the `<!-- -->` notes with real content). Ground every REST detail in `docs/superpowers/research/nim-rest-contract.md`.

```markdown
---
name: datarobot-deploy-nim
description: Deploy an NVIDIA NIM on DataRobot with a GPU resource bundle and expose it as an MCP tool. Use when someone wants to stand up a NIM (e.g. a CoPilot model) and call it as a tool from an assistant, including choosing GPU resources.
---

# DataRobot Deploy NIM Skill

## Quick Start
<!-- discover (C1) -> create from template (C2) -> register+deploy (C3) -> expose via register-mcp-tool -->

## Prerequisites
<!-- feature flags NIM_MODELS + MLOPS_RESOURCE_REQUEST_BUNDLES; NGC API key stored as a secureConfig (secretConfigId); how to check each -->

## Step 1 — Discover the NIM template + GPU bundle
<!-- discover_nim_options.py; explain templateSubType=NIM_CONTAINERS and customModel GPU bundles -->

## Step 2 — Create the NIM model
<!-- create_nim_from_template.py; POST customModels/fromModelTemplate/; returns customModelId + customModelVersionId -->

## Step 3 — Register + deploy to a serverless GPU PE
<!-- deploy_nim.py; modelPackages/fromCustomModelVersion -> deployments/fromModelPackage; serverless PE selection -->

## Step 4 — Expose as a tool
<!-- hand off to datarobot-register-mcp-tool; NIM auto-detects as chat, no schema authoring -->

## Scripts
- `scripts/discover_nim_options.py` — list NIM templates + GPU resource bundles
- `scripts/create_nim_from_template.py` — create the NIM model from a template (REST)
- `scripts/deploy_nim.py` — register the version + deploy to a serverless GPU PE (REST)
```

**Suggested trigger phrases:** "deploy a NIM on DataRobot and use it as a tool", "stand up CoPilot/an NVIDIA NIM with a GPU", "what GPU bundle do I need for this NIM", "expose my NIM to Claude over MCP".

- [ ] **Step 2: Add the gemini-extension.json entry** for `datarobot-deploy-nim` (`path` = `skills/datarobot-deploy-nim/SKILL.md`), matching the format of existing entries. **Also add the `docs/.well-known/ai-catalog.json` entry** (`identifier` urn suffix `deploy-nim`, `displayName` `datarobot-deploy-nim`, `url` the github blob to its SKILL.md, `description`, and 3 `representativeQueries` from the trigger phrases) — matching the shape of existing catalog entries.

- [ ] **Step 3: Verify structural + plugin + catalog tests.** Run: `uv run pytest tests/integration/test_skills.py tests/integration/test_plugins.py tests/integration/test_catalog.py -k "deploy-nim or all_skills_included or catalog" -v` (pytest IDs use hyphens). Expected: PASS. (Skip the `*_validate` CLI tests.)

- [ ] **Step 4: Commit.** `git add skills/datarobot-deploy-nim/SKILL.md skills/datarobot-deploy-nim/scripts/ gemini-extension.json docs/.well-known/ai-catalog.json && git commit -m "docs(deploy-nim): author SKILL.md + gemini + catalog entries"`.

## Final verification

- [ ] Run `task lint` — all copyright/format/naming/structure checks pass.
- [ ] Run `uv run pytest tests/integration -q` — plugin version consistency, codeowners, skill structure all pass.
- [ ] Run `uv run --group e2e pytest tests/e2e/ -v` — LLM judge passes for all three new skills; live test runs if env is set, else skips.
- [ ] Confirm `CHANGELOG.md` `[Unreleased]` has all three entries and version is `1.4.0` in all four manifests.
- [ ] Open PR; after merge, send the mlops Slack hand-off re: ownership of `datarobot-deploy-nim` (and possibly the MCP skills).

## Self-review notes (coverage vs spec)

- Spec "Skill 1" → Phase B (B1–B6). "Skill 2" → Phase C. "Skill 3" → Phase A.
- Spec "surfacing differs by server" → B3 (`self_hosted_register_url`) + B5 prose + B4/B6 verify.
- Spec "feature flag, no public write" → B2 (read + guidance, never claims to flip).
- Spec "interface envelope rules" → A1 validator mirroring `schema.py`.
- Spec "NIM hybrid, UI import" → Phase C reality note + C4 Step 1 live validation.
- Spec "one plugin, three skills, core-modeling, real e2e" → Task 0 + B6.
- **Known deferred wiring:** `verify_mcp_tool.list_tools` (B4) and the NIM REST shapes (C3) are implemented against best-grounded assumptions and explicitly confirmed against live APIs in B6/C4 — flagged, not placeheld.
