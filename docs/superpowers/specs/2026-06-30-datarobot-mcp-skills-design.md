# Design: DataRobot MCP Tool Skills

**Date:** 2026-06-30
**Status:** Approved (design) — pending implementation plan
**Author:** Jeremy Johnson

## Problem

Customers want to use a DataRobot deployment — a predictive model, an agent, or an
NVIDIA NIM (e.g. a CoPilot model) — as a **tool** from an MCP client (Claude Code,
Cursor, etc.). DataRobot already supports this: the **Global MCP Server** auto-exposes
tagged deployments as MCP tools, and the **self-hosted "user MCP"** (the
`af-component-datarobot-mcp` App Framework component / agent application template) does
the same. But customers don't know this capability exists, so instead of using it they
ask their assistant to write bespoke HTTP glue to call the deployment. The result is
reinvented, fragile, per-customer tooling for a problem the platform already solves.

These skills teach an assistant the correct, platform-native path so the task is
one-shot reliable instead of improvised.

## Grounded mechanism (verified against source)

This design is anchored on the actual implementation of `datarobot-oss/datarobot-genai`,
`datarobot/global-mcp`, and `datarobot-community/af-component-datarobot-mcp`.

- **Two MCP server targets.**
  - **Hosted Global MCP Server** — platform-wide endpoint
    `https://<host>/api/v2/genai/globalmcp/mcp`. The customer connects; they do not run it.
  - **Self-hosted "user MCP"** — the customer deploys
    `af-component-datarobot-mcp` (often via the agent application template) as a custom
    application. Per-deployment endpoint `https://<host>/deployments/<id>/directAccess/mcp/`.
- **Deployment → tool selection is a tag.** Both servers expose any deployment tagged
  **`tool` = `tool`** (`datarobot_genai/drmcpbase/datarobot_services/client.py`,
  `_list_mcp_tool_custom_model_deployment_ids`, query `?tagKeys=tool&tagValues=tool`).
  There is no SDK "register" call — tagging is the registration.
- **Surfacing after tagging differs by server** (this is the crux of the lifecycle):
  - *Hosted Global MCP:* `CustomModelToolProvider._list_tools()` re-runs the tag query on
    **every `tools/list`** request. No server restart, no server-side register call. The
    *client* must refresh/reconnect (or receive `notifications/tools/list_changed`) for the
    new tool to appear.
  - *Self-hosted:* discovers tagged deployments **at startup** when
    `MCP_SERVER_REGISTER_DYNAMIC_TOOLS_ON_STARTUP=true`, **or** picks up a newly-tagged
    deployment at runtime via `PUT /registeredDeployments/{deployment_id}`
    (`GET`/`DELETE` siblings). So: restart **or** call the register API.
- **The interface = a JSON-Schema envelope.** Authored in the custom model's
  `model-metadata.yaml` field **`inputSchema`** (requires `datarobot-drum >= 1.17.2`),
  read by the server from the deployment's `/directAccess/info/` endpoint and parsed by
  `datarobot_genai/drmcpbase/dynamic_tools/schema.py:create_input_schema_pydantic_model`.
  Exactly four top-level keys are allowed: `path_params`, `query_params`, `data`, `json`
  (mapping to HTTP request parts). Rules: `path_params`/`query_params` flat; `data` nested
  with string primitives; `json` arbitrary; `$ref`/`$defs` supported; empty schemas
  rejected unless `MCP_SERVER_TOOL_REGISTRATION_ALLOW_EMPTY_SCHEMA=true`. There is no
  declared output schema — the HTTP response body is returned as-is.
- **Most deployments need no hand-authored schema.** Predictive models get a fallback
  `{"data": "<CSV string>"}`. Agentic (`agenticworkflow`) and any deployment with
  `supports_chat_api == True` (NIM-served, Guarded RAG, LLM blueprints) are auto-routed to
  `/chat/completions` with an OpenAI-style chat schema. Hand-authoring is required only for
  **custom (non-chat) I/O** — REST-shaped tools, custom unstructured models.
- **Feature flag (hosted only).** The Global MCP dynamic-tool provider is gated by
  `ENABLE_MCP_TOOLS_GALLERY_SUPPORT` (ALPHA). It is **readable** by any user via
  `POST /api/v2/entitlements/evaluate/` but has **no public/SDK write** — cloud customers
  need DataRobot to enable it; on-prem org admins can toggle it. The **self-hosted user MCP
  does not check this flag**, so self-hosting is the unblocked path for gated customers.
- **NIM creation is hybrid, not pure-SDK.** The NGC gallery import (which creates the NIM
  registered model and recommends the GPU resource bundle) is **UI-only / private API**.
  Binding `resourceBundleId` to a model version is **REST-only**
  (`POST /api/v2/customModels/{id}/versions/`), not exposed in the SDK. What *is*
  SDK-scriptable: listing GPU bundles (`ResourceBundle.list(use_cases=["customModel"])`,
  read-only), deploying a registered model to a serverless GPU prediction environment
  (`Deployment.create_from_registered_model_version(..., prediction_environment_id=...)`),
  and tagging. So a NIM skill must orchestrate a UI step + SDK/REST steps; it cannot be
  fully headless.

## The skills

Three composable skills under the required `datarobot-` prefix. `datarobot-register-mcp-tool`
is the entry point and ships first; the other two build on it.

### Skill 1 — `datarobot-register-mcp-tool` (ship first)

**Purpose:** take an *existing* deployment and make it callable as an MCP tool.

**Trigger phrases (expected):** "use my DataRobot deployment as a tool", "expose this
deployment to Claude/Cursor", "register deployment X as an MCP tool".

**Flow:**
1. **Classify** the deployment: structured-predictive / custom-DRUM / agentic / chat-NIM
   (via target type + `/capabilities/` `supports_chat_api`).
2. **Interface check:** predictive, agentic, and chat/NIM use auto-fallbacks — confirm and
   move on. For custom non-chat I/O, invoke `datarobot-define-tool-schema` to author and
   validate `inputSchema`, then push a new custom model version.
3. **Tag** the deployment `tool=tool` via the SDK.
4. **Surface** per target:
   - *Hosted:* instruct/verify a client reconnect so the new tool appears.
   - *Self-hosted:* call `PUT /registeredDeployments/{id}` (preferred, no downtime) or
     document the restart path.
5. **Feature-flag check (hosted):** read `ENABLE_MCP_TOOLS_GALLERY_SUPPORT` via
   `entitlements/evaluate`. If off, explain the enablement path (on-prem admin toggle;
   cloud → DataRobot/support, flag name + PBMP-7644) and offer the self-hosted route as the
   unblocked alternative. The skill does **not** claim it can flip the flag.
6. **Verify end-to-end:** connect to the right MCP endpoint, confirm the tool is in
   `tools/list`, and run a test invocation.
7. **Emit client config** for Claude/Cursor pointed at the correct endpoint (hosted
   `/api/v2/genai/globalmcp/mcp` vs self-hosted `…/deployments/{id}/directAccess/mcp/`),
   with `Authorization: Bearer <token>`.

**Inputs:** deployment id (or enough to find it), target server (hosted | self-hosted),
client to configure. **Output:** a registered, verified tool + ready-to-paste client config.

### Skill 2 — `datarobot-deploy-nim`

**Purpose:** deploy an NVIDIA NIM (with GPU) and expose it as a tool. Hybrid by necessity.

**Flow:**
1. **Guide the NGC import (UI):** the skill clearly walks the user through
   `Registry > Models > Import from NVIDIA NGC` (prerequisites: GenAI/GPU entitlement +
   org NGC API key), since this step is not SDK-scriptable. It states plainly what is
   manual and why.
2. **GPU resource bundle:** discover candidates via
   `ResourceBundle.list(use_cases=["customModel"])` filtered on `has_gpu`/`gpu_maker`,
   help the user select, and sanity-check (bundles are operator-defined per cluster; the
   skill flags that cluster GPU capacity is an infra concern with no public quota API).
   Bind `resourceBundleId` via REST where the SDK can't.
3. **Deploy** the registered NIM model to a serverless GPU prediction environment via the
   SDK.
4. **Expose:** NIM auto-detects as chat (`supports_chat_api`) — no schema authoring — so
   hand off to `datarobot-register-mcp-tool` to tag + surface + verify.

**Inputs:** chosen NIM, target server. **Output:** a deployed NIM exposed as a verified tool.

### Skill 3 — `datarobot-define-tool-schema`

**Purpose:** author and validate the `model-metadata.yaml inputSchema` that makes a custom
deployment callable. Shared component of skills 1 and 2.

**Flow:**
1. Explain the envelope contract (`path_params`/`query_params`/`data`/`json`) and which
   HTTP part each maps to.
2. From the deployment's real request shape, generate a correct `inputSchema`.
3. Validate against the same rules `schema.py` enforces (allowed keys, flatness of
   path/query, string-primitive `data`, `$ref`/`$defs`, non-empty) so failures surface
   before deploy, not after.
4. Note the `datarobot-drum >= 1.17.2` requirement and where the field lives in
   `model-metadata.yaml`.

**Inputs:** a description of the deployment's request/response. **Output:** a validated
`inputSchema` ready to drop into `model-metadata.yaml`.

## Cross-cutting concerns

- **Auth/config:** all paths use `DATAROBOT_API_TOKEN` + `DATAROBOT_ENDPOINT`; clients
  connect over streamable-HTTP with `Authorization: Bearer <token>`. On credential
  failure, defer to `datarobot-setup` per repo convention.
- **Hosted vs self-hosted** is a first-class branch in skill 1, surfaced to the user early
  because it changes the surfacing mechanism, the endpoint, and whether the feature flag
  applies.
- **Honesty about manual/gated steps:** the NGC import (skill 2) and the feature-flag
  enablement (skill 1) are explicitly called out as not-automatable, with the real path to
  resolution, rather than papered over.

## Out of scope

- Migrating the repo from the `datarobot-` prefix to `dr-` (would require editing
  `tests/integration/test_skills.py`, `test_plugins.py`, `CLAUDE.md`, and renaming all 12
  existing skills). Tracked separately if desired.
- Reverse-engineering the private NGC-import REST endpoint for a fully headless NIM import.
- Authoring/output-schema validation beyond what `schema.py` enforces (the server declares
  no output schema).

## Open items to resolve during planning

1. **CODEOWNERS — decided.** All three skills are assigned to `@datarobot/core-modeling`
   for now so they can merge. **Follow-up:** Slack the mlops team to ask whether they'll
   take ownership — `datarobot-deploy-nim` is most clearly theirs, and possibly the MCP
   skills too, since NIMs/serving are their domain. Re-point the `CODEOWNERS` entries if
   they accept.
2. **Packaging — decided.** Three distinct skills, shipped as a **single plugin** (one
   version bump from Claude's perspective). Follow `CONTRIBUTING.md` for the version/changelog.
3. **CI / e2e — decided.** Each skill gets common trigger phrases for the LLM-judge suite.
   In addition, at least **one e2e test exercises a real deployment** (tag → surface →
   `tools/list` → test invocation), not just a stub. Requires a test deployment +
   `DATAROBOT_ENDPOINT`/`DATAROBOT_API_TOKEN` in CI.

## Risks

- The feature flag is ALPHA; behavior/name could change. Skill 1 must read it dynamically,
  not hardcode assumptions.
- NIM import being UI-only means skill 2 can't be fully one-shot; its value is correctness
  and GPU-bundle guidance, not full automation. Set that expectation in the skill.
- Self-hosted endpoint/port conventions vary slightly between template docs (8080 vs 9000);
  skill 1 should read the actual deploy output, not assume a port.
