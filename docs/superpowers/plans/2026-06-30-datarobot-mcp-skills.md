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
- **SKILL.md prose is authored by the human maintainer** (per `CLAUDE.md`). Plan tasks provide the frontmatter + section skeleton + trigger phrases; the human fills prose. Scripts/tests/references are agent-built.
- Version bump: `1.3.2` → `1.4.0` (minor: new skills) in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `gemini-extension.json`. Add `CHANGELOG.md` entries under `[Unreleased]`.

---

## Phase 0 — Scaffolding

### Task 0: Create skill dirs, CODEOWNERS, version bump, changelog

**Files:**
- Create: `skills/datarobot-define-tool-schema/scripts/.gitkeep`, `skills/datarobot-register-mcp-tool/scripts/.gitkeep`, `skills/datarobot-deploy-nim/scripts/.gitkeep`
- Modify: `.github/CODEOWNERS`, `.claude-plugin/plugin.json:4`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json:4`, `gemini-extension.json:3`, `CHANGELOG.md`
- Test: `tests/integration/test_codeowners.py` (existing), `tests/integration/test_plugins.py` (existing)

**Interfaces:**
- Produces: three skill directories the later tasks populate.

- [ ] **Step 1: Create the three skill+scripts directories** with a `.gitkeep` in each `scripts/` so empty dirs commit.

- [ ] **Step 2: Add CODEOWNERS entries** under the core-modeling block in `.github/CODEOWNERS`:

```
/skills/datarobot-define-tool-schema/ @datarobot/core-modeling
/skills/datarobot-register-mcp-tool/ @datarobot/core-modeling
/skills/datarobot-deploy-nim/ @datarobot/core-modeling
```

- [ ] **Step 3: Bump version `1.3.2` → `1.4.0`** in all four manifest files (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `gemini-extension.json`).

- [ ] **Step 4: Add CHANGELOG entries** under `## [Unreleased]`:

```markdown
- `datarobot-define-tool-schema`: New skill — author and validate the `model-metadata.yaml inputSchema` that makes a custom deployment callable as an MCP tool.
- `datarobot-register-mcp-tool`: New skill — register an existing deployment as an MCP tool (tag, surface on hosted/self-hosted MCP, feature-flag check, verify, emit client config).
- `datarobot-deploy-nim`: New skill — deploy an NVIDIA NIM with a GPU resource bundle and expose it as an MCP tool.
```

- [ ] **Step 5: Run structural tests.** Run: `uv run pytest tests/integration/test_plugins.py tests/integration/test_codeowners.py -q`. Expected: `test_codeowners` will FAIL for the three new dirs until their `SKILL.md` exists (codeowners test only parametrizes dirs that already have `SKILL.md`, so it passes now); `test_plugins` PASSES with matching versions. Confirm version-consistency assertions pass.

- [ ] **Step 6: Commit.**

```bash
git add .github/CODEOWNERS .claude-plugin .cursor-plugin gemini-extension.json CHANGELOG.md skills/datarobot-*/scripts/.gitkeep
git commit -m "scaffold: add three MCP tool skill dirs, codeowners, v1.4.0 bump"
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
    if len(argv) >= 3 and argv[1] == "--schema":
        schema = json.loads(argv[2])
    elif len(argv) >= 2:
        schema = _load(argv[1])
    else:
        print(__doc__)
        return 2
    errors = validate_tool_schema(schema)
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

### Task A2: Author `SKILL.md` (HUMAN-AUTHORED prose)

**Files:**
- Create: `skills/datarobot-define-tool-schema/SKILL.md`
- Test: `tests/integration/test_skills.py`, `tests/e2e/test_skills_e2e.py`

**Interfaces:**
- Consumes: `scripts/validate_tool_schema.py` (referenced in prose).

- [ ] **Step 1: Drop in this frontmatter + section skeleton** (the maintainer writes the prose under each heading):

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

- [ ] **Step 2: Verify structural tests pass.** Run: `uv run pytest tests/integration/test_skills.py -k define_tool_schema -v`. Expected: name-matches-folder, description-has-"Use when", and token-count assertions PASS.

- [ ] **Step 3: Commit** (maintainer commits their prose). `git add skills/datarobot-define-tool-schema/SKILL.md && git commit -m "docs(define-tool-schema): author SKILL.md"`.

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

### Task B5: Author `SKILL.md` (HUMAN-AUTHORED prose)

**Files:**
- Create: `skills/datarobot-register-mcp-tool/SKILL.md`
- Test: `tests/integration/test_skills.py`, `tests/e2e/test_skills_e2e.py`

- [ ] **Step 1: Drop in frontmatter + skeleton.**

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

- [ ] **Step 2: Verify structural tests.** Run: `uv run pytest tests/integration/test_skills.py -k register_mcp_tool -v`. Expected: PASS.

- [ ] **Step 3: Commit** (maintainer). `git add skills/datarobot-register-mcp-tool/SKILL.md && git commit -m "docs(register-mcp-tool): author SKILL.md"`.

### Task B6: Real-deployment e2e test

**Files:**
- Create: `tests/e2e/test_register_mcp_tool_live.py`
- Modify: `.env.example` (document any new vars, e.g. `E2E_TEST_DEPLOYMENT_ID`)

**Interfaces:**
- Consumes: `register_deployment_tool.tag_as_tool`, `verify_mcp_tool.list_tools`/`assert_tool_present`.

> This is the one functional test that exercises a real deployment end-to-end. It is **skipped unless** `DATAROBOT_ENDPOINT`, `DATAROBOT_API_TOKEN`, and `E2E_TEST_DEPLOYMENT_ID` are set, so default CI/local runs stay green.

- [ ] **Step 1: Write the test.**

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
    assert assert_tool_present(dep_id, tools), (
        "deployment tagged but not present in tools/list — "
        "check ENABLE_MCP_TOOLS_GALLERY_SUPPORT and client/list caching"
    )
```

- [ ] **Step 2: Implement `verify_mcp_tool.list_tools` against the live MCP client** (this is where the deferred B4 wiring lands). Confirm the deployment-id↔tool mapping shape; adjust `tool_name_for_deployment`'s `meta` key if the live payload differs, and update B4's unit tests to match the real shape.

- [ ] **Step 3: Run against a real deployment.** Run: `E2E_TEST_DEPLOYMENT_ID=<id> uv run --group e2e pytest tests/e2e/test_register_mcp_tool_live.py -v`. Expected: PASS (tool present). Capture output.

- [ ] **Step 4: Confirm it skips cleanly without env.** Run: `uv run --group e2e pytest tests/e2e/test_register_mcp_tool_live.py -v`. Expected: SKIPPED.

- [ ] **Step 5: Commit.** `git add tests/e2e/test_register_mcp_tool_live.py .env.example skills/datarobot-register-mcp-tool/scripts/verify_mcp_tool.py skills/datarobot-register-mcp-tool/scripts/test_verify_mcp_tool.py && git commit -m "test(register-mcp-tool): live deployment registration e2e"`.

**MILESTONE: skills #3 and #1 are shippable here.** Run `task lint && uv run pytest tests/integration -q` before opening the PR.

---

## Phase C — `datarobot-deploy-nim`

> **Reality (from research):** the NGC gallery import that creates the NIM registered model is **UI-only**, and binding `resourceBundleId` to a model version is **REST-only** (not in the SDK). This skill orchestrates a guided UI step + SDK/REST steps; it is correctness-and-guidance, not full headless automation. The REST shapes below MUST be confirmed against a live tenant during Task C4.

### Task C1: GPU bundle discovery (`list_gpu_bundles.py`)

**Files:**
- Create: `skills/datarobot-deploy-nim/scripts/list_gpu_bundles.py`
- Test: `skills/datarobot-deploy-nim/scripts/test_list_gpu_bundles.py`

**Interfaces:**
- Produces: `filter_gpu_bundles(bundles: list) -> list` — keep only `has_gpu` bundles, sorted by `gpu_count` then `gpu_memory_bytes`. `bundles` items expose `.has_gpu`, `.gpu_count`, `.gpu_memory_bytes`, `.id`, `.name`.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from list_gpu_bundles import filter_gpu_bundles


class _B:
    def __init__(self, id, has_gpu, gpu_count=0, gpu_memory_bytes=0):
        self.id, self.name = id, id
        self.has_gpu = has_gpu
        self.gpu_count = gpu_count
        self.gpu_memory_bytes = gpu_memory_bytes


def test_filters_non_gpu():
    out = filter_gpu_bundles([_B("cpu", False), _B("g1", True, 1, 10)])
    assert [b.id for b in out] == ["g1"]


def test_sorts_by_gpu_count_then_memory():
    out = filter_gpu_bundles([
        _B("g2", True, 2, 10), _B("g1a", True, 1, 80), _B("g1b", True, 1, 40)])
    assert [b.id for b in out] == ["g1b", "g1a", "g2"]
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_list_gpu_bundles.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""List GPU resource bundles available for custom models.

Usage:
    python list_gpu_bundles.py
"""
import os
import sys


def filter_gpu_bundles(bundles: list) -> list:
    gpu = [b for b in bundles if getattr(b, "has_gpu", False)]
    return sorted(gpu, key=lambda b: (b.gpu_count, b.gpu_memory_bytes))


def main(argv: list[str]) -> int:
    import datarobot as dr
    from datarobot.models.resource_bundle import ResourceBundle

    dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
              endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))
    bundles = ResourceBundle.list(use_cases=["customModel"])
    for b in filter_gpu_bundles(bundles):
        print(f"{b.id}\t{b.name}\tgpu_count={b.gpu_count}\tgpu_mem={b.gpu_memory_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_list_gpu_bundles.py -v`. Expected: 2 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-deploy-nim/scripts/list_gpu_bundles.py skills/datarobot-deploy-nim/scripts/test_list_gpu_bundles.py && git commit -m "feat(deploy-nim): GPU resource bundle discovery"`.

### Task C2: Deploy a registered NIM model (`deploy_registered_nim.py`)

**Files:**
- Create: `skills/datarobot-deploy-nim/scripts/deploy_registered_nim.py`
- Test: `skills/datarobot-deploy-nim/scripts/test_deploy_registered_nim.py`

**Interfaces:**
- Produces: `deploy_kwargs(model_package_id: str, label: str, prediction_environment_id: str) -> dict` — builds the kwargs for `Deployment.create_from_registered_model_version`, enforcing that a `prediction_environment_id` (serverless GPU PE) is provided and never paired with a `default_prediction_server_id`.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from deploy_registered_nim import deploy_kwargs


def test_kwargs_include_pe_and_package():
    kw = deploy_kwargs("pkg1", "my-nim", "pe123")
    assert kw["model_package_id"] == "pkg1"
    assert kw["label"] == "my-nim"
    assert kw["prediction_environment_id"] == "pe123"
    assert "default_prediction_server_id" not in kw


def test_requires_prediction_environment():
    with pytest.raises(ValueError):
        deploy_kwargs("pkg1", "my-nim", "")
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_deploy_registered_nim.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Deploy a registered NIM model to a serverless GPU prediction environment.

Prereq: the NIM registered model already exists (created via the NGC gallery
import in the DataRobot UI — that step is not SDK-scriptable) and its model
version is bound to a GPU resource bundle.

Usage:
    python deploy_registered_nim.py --model-package-id <id> --label <name> \
        --prediction-environment-id <pe_id>
"""
import argparse
import os
import sys


def deploy_kwargs(model_package_id: str, label: str, prediction_environment_id: str) -> dict:
    if not prediction_environment_id:
        raise ValueError("a serverless GPU prediction_environment_id is required for NIM")
    return {
        "model_package_id": model_package_id,
        "label": label,
        "prediction_environment_id": prediction_environment_id,
    }


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("--model-package-id", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--prediction-environment-id", required=True)
    args = p.parse_args(argv[1:])

    dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
              endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))
    kwargs = deploy_kwargs(args.model_package_id, args.label, args.prediction_environment_id)
    deployment = dr.Deployment.create_from_registered_model_version(**kwargs)
    print(f"Deployed NIM as deployment {deployment.id}. "
          "Next: run datarobot-register-mcp-tool to expose it (NIM auto-detects as chat).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_deploy_registered_nim.py -v`. Expected: 2 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-deploy-nim/scripts/deploy_registered_nim.py skills/datarobot-deploy-nim/scripts/test_deploy_registered_nim.py && git commit -m "feat(deploy-nim): deploy registered NIM to serverless GPU PE"`.

### Task C3: REST escape hatch to bind a resource bundle (`bind_resource_bundle.py`)

**Files:**
- Create: `skills/datarobot-deploy-nim/scripts/bind_resource_bundle.py`
- Test: `skills/datarobot-deploy-nim/scripts/test_bind_resource_bundle.py`

**Interfaces:**
- Produces: `bind_payload(base_environment_id: str, resource_bundle_id: str) -> dict` — the body for `POST /customModels/{id}/versions/` that creates a new version carrying `resourceBundleId` (SDK omits this field, so we post raw).

> **Live-API note:** confirm the exact request key (`resourceBundleId`) and whether a new version requires `baseEnvironmentId`/`isMajorUpdate` against the tenant in Task C4 before relying on this in prose.

- [ ] **Step 1: Write failing tests.**

```python
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from bind_resource_bundle import bind_payload


def test_payload_carries_resource_bundle_id():
    body = bind_payload("env1", "bundleG")
    assert body["resourceBundleId"] == "bundleG"
    assert body["baseEnvironmentId"] == "env1"


def test_payload_marks_major_update():
    body = bind_payload("env1", "bundleG")
    assert body["isMajorUpdate"] is True
```

- [ ] **Step 2: Run to verify failure.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_bind_resource_bundle.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Bind a GPU resource bundle to a custom model version via the REST API.

The public SDK's CustomModelVersion.create_* paths do not send resourceBundleId,
so this posts the raw API call. Confirm the request shape against your tenant.

Usage:
    python bind_resource_bundle.py --custom-model-id <id> \
        --base-environment-id <env> --resource-bundle-id <bundle>
"""
import argparse
import os
import sys


def bind_payload(base_environment_id: str, resource_bundle_id: str) -> dict:
    return {
        "isMajorUpdate": True,
        "baseEnvironmentId": base_environment_id,
        "resourceBundleId": resource_bundle_id,
    }


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("--custom-model-id", required=True)
    p.add_argument("--base-environment-id", required=True)
    p.add_argument("--resource-bundle-id", required=True)
    args = p.parse_args(argv[1:])

    client = dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
                       endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))
    body = bind_payload(args.base_environment_id, args.resource_bundle_id)
    resp = client.post(f"customModels/{args.custom_model_id}/versions/", data=body)
    print(f"Created version with resource bundle {args.resource_bundle_id} "
          f"(status {resp.status_code}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run to verify pass.** Run: `cd skills/datarobot-deploy-nim/scripts && uv run pytest test_bind_resource_bundle.py -v`. Expected: 2 passed.

- [ ] **Step 5: Commit.** `git add skills/datarobot-deploy-nim/scripts/bind_resource_bundle.py skills/datarobot-deploy-nim/scripts/test_bind_resource_bundle.py && git commit -m "feat(deploy-nim): REST resource-bundle binding escape hatch"`.

### Task C4: Author `SKILL.md` (HUMAN-AUTHORED prose) + live validation

**Files:**
- Create: `skills/datarobot-deploy-nim/SKILL.md`
- Test: `tests/integration/test_skills.py`

- [ ] **Step 1: Live-validate the REST shapes.** Against a real tenant with NIM access, confirm: (a) `ResourceBundle.list(use_cases=["customModel"])` returns GPU bundles; (b) the `POST customModels/{id}/versions/` body key is `resourceBundleId`; (c) `create_from_registered_model_version` deploys to a serverless GPU PE. Adjust C2/C3 code + tests to match reality. Capture the working command output.

- [ ] **Step 2: Drop in frontmatter + skeleton.**

```markdown
---
name: datarobot-deploy-nim
description: Deploy an NVIDIA NIM on DataRobot with a GPU resource bundle and expose it as an MCP tool. Use when someone wants to stand up a NIM (e.g. a CoPilot model) and call it as a tool from an assistant, including selecting GPU resources.
---

# DataRobot Deploy NIM Skill

## Quick Start
<!-- maintainer: NGC import (UI) -> pick GPU bundle -> deploy to serverless GPU PE -> expose via register-mcp-tool -->

## Step 1 — Import the NIM (UI, required)
<!-- maintainer: Registry > Models > Import from NVIDIA NGC; prereqs: GenAI/GPU entitlement + org NGC API key; why this step is manual -->

## Step 2 — Choose a GPU resource bundle
<!-- maintainer: list_gpu_bundles.py; bundles are operator-defined; cluster GPU capacity is an infra concern (no public quota API) -->

## Step 3 — Deploy to a serverless GPU prediction environment
<!-- maintainer: deploy_registered_nim.py; bind_resource_bundle.py if needed -->

## Step 4 — Expose as a tool
<!-- maintainer: hand off to datarobot-register-mcp-tool; NIM auto-detects as chat, no schema authoring -->

## Scripts
- `scripts/list_gpu_bundles.py` — list GPU resource bundles for custom models
- `scripts/deploy_registered_nim.py` — deploy a registered NIM to a serverless GPU PE
- `scripts/bind_resource_bundle.py` — REST: bind a GPU bundle to a model version
```

**Suggested trigger phrases:** "deploy a NIM on DataRobot and use it as a tool", "stand up CoPilot/an NVIDIA NIM with a GPU", "what GPU bundle do I need for this NIM", "expose my NIM to Claude over MCP".

- [ ] **Step 3: Verify structural tests.** Run: `uv run pytest tests/integration/test_skills.py -k deploy_nim -v`. Expected: PASS.

- [ ] **Step 4: Commit** (maintainer). `git add skills/datarobot-deploy-nim/SKILL.md skills/datarobot-deploy-nim/scripts/ && git commit -m "docs(deploy-nim): author SKILL.md + live-validated REST shapes"`.

---

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
