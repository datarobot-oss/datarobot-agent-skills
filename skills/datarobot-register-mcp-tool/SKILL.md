---
name: datarobot-register-mcp-tool
description: Register an existing DataRobot deployment (predictive, agent, or NIM) as an MCP tool so assistants call it natively instead of writing custom glue. Use when someone wants to use a DataRobot deployment as a tool in Claude/Cursor, expose a deployment to an MCP client, or asks why a tagged deployment isn't showing up.
---

# DataRobot Register MCP Tool Skill

This skill walks you through tagging a DataRobot deployment so that MCP clients — Claude, Cursor, or any other Model Context Protocol consumer — can discover and call it as a native tool. Registration is a single deployment tag. Everything else in this skill explains how to surface that tool to your client and verify it works.

**Setup.** `DATAROBOT_ENDPOINT` (ending in `/api/v2`) and `DATAROBOT_API_TOKEN` must be set, and the `datarobot` Python SDK must be installed. If either is missing, run the `datarobot-setup` skill first — it installs the SDK, configures credentials, and validates authentication. Do this before the steps below.

## Quick Start

These four steps take a deployment from unregistered to callable in Claude or Cursor.

**Step 1 — Tag the deployment.** Run the registration script with your deployment ID:

```bash
python scripts/register_deployment_tool.py <deployment_id>
```

This sets tag name `tool` with value `tool` on the deployment using the DataRobot Python SDK. Both the hosted global MCP server and the self-hosted user MCP server use this exact tag to discover which deployments to expose.

If you are using a **self-hosted** MCP server, pass its URL so the script also registers the deployment at runtime without restarting the server:

```bash
python scripts/register_deployment_tool.py <deployment_id> \
  --self-hosted-mcp-url https://<host>/deployments/<mcp_server_deployment_id>/directAccess/mcp/
```

Note: `<mcp_server_deployment_id>` is the ID of the running self-hosted MCP server deployment, not the `<deployment_id>` of the deployment you are exposing as a tool.

**Step 2 — Surface the tool.** The mechanism differs by server target:

- *Hosted global MCP server:* No server action needed. The server re-reads tagged deployments on every `tools/list` request. Reconnect your MCP client (Claude Desktop: quit and relaunch; Cursor: reload the MCP config) and the tool appears.
- *Self-hosted user MCP:* If you passed `--self-hosted-mcp-url` in the tag step, the runtime registration already happened — nothing more is needed. Otherwise, restart the server (with `MCP_SERVER_REGISTER_DYNAMIC_TOOLS_ON_STARTUP=true`) or re-run the script with `--self-hosted-mcp-url`.

**Step 3 — Verify.** Confirm the deployment appears in `tools/list`:

```bash
python scripts/verify_mcp_tool.py <deployment_id> --mcp-url https://<host>/api/v2/genai/globalmcp/mcp
```

Exit code 0 means the tool is live. A non-zero exit prints what was actually returned so you can diagnose the mismatch.

**Step 4 — Connect your client.** Print the MCP config block your client needs:

```bash
# Hosted global MCP server
python scripts/emit_client_config.py --host <host> --hosted

# Self-hosted per-deployment server
python scripts/emit_client_config.py --host <host> --self-hosted --deployment-id <deployment_id>
```

Paste the output into Claude Desktop's `claude_desktop_config.json` or Cursor's MCP settings. Clients authenticate with `Authorization: Bearer <DATAROBOT_API_TOKEN>` over streamable-HTTP.

## Hosted Global MCP vs Self-Hosted User MCP

DataRobot provides two distinct MCP server targets. You connect to one or both depending on your access and requirements.

**Hosted Global MCP Server** is a platform-managed, multi-tenant endpoint. Its URL is `https://<host>/api/v2/genai/globalmcp/mcp`. You do not run or maintain this server — DataRobot operates it. All deployments tagged `tool=tool` across your organization appear here automatically on the next `tools/list` call. The trade-off is that a platform feature flag (`ENABLE_MCP_TOOLS_GALLERY_SUPPORT`) must be active; see the Feature Flag section below.

**Self-Hosted User MCP** is a server you run yourself using the `af-component-datarobot-mcp` App Framework component or the DataRobot agent application template. Each deployment gets its own per-deployment endpoint: `https://<host>/deployments/<id>/directAccess/mcp/`. You control the server lifecycle, so there is no platform feature flag gating your access. This is the unblocked path if the hosted flag is off or if you need per-deployment isolation.

Choose the hosted server when you want a single MCP endpoint that aggregates all registered tools with zero server-side ops. Choose self-hosted when you need guaranteed access today, want fine-grained control over which tools are exposed, or are running in an on-premises environment where the hosted server is not available.

## Deployment Types

The MCP server generates a callable interface for each tagged deployment. For most deployment types this happens automatically.

**Standard predictive models** (AutoML, registered tabular models): the server generates a fallback schema of `{"data": "<CSV>"}`. No additional configuration is needed.

**Agentic workflow deployments** (target type `agenticworkflow`) and **chat or NIM deployments** (any deployment where `supports_chat_api` is true): the server generates an automatic OpenAI chat-style interface at `/chat/completions`. No schema authoring is needed.

**Custom non-chat deployments** with a hand-authored scoring hook that accepts an arbitrary request body: you must define an `inputSchema` in `model-metadata.yaml` before the MCP server can expose a callable interface. Use the sibling skill `datarobot-define-tool-schema` for this step. Once the schema is in place, come back here to tag and surface the deployment.

If you are unsure which category your deployment falls into, check the **Target Type** field on the deployment overview page in the DataRobot UI. If the card shows a Chat tab, it qualifies for the automatic chat-style interface.

## After Tagging: Making the Tool Appear

Tagging is necessary but not sufficient — the tool must also be surfaced to your MCP client. The mechanism differs between the two server targets.

**Hosted global MCP server:** The server reads the list of tagged deployments fresh on every incoming `tools/list` request. There is no server-side registration call and no server restart. The only action required is on the client side: close and reopen the MCP connection. In Claude Desktop this means quitting and relaunching the application. In Cursor it means reloading the MCP configuration from settings.

**Self-hosted user MCP:** The server discovers tagged deployments at startup when the environment variable `MCP_SERVER_REGISTER_DYNAMIC_TOOLS_ON_STARTUP=true` is set. For a deployment tagged after the server started, you have two options:

1. Pass `--self-hosted-mcp-url` to `register_deployment_tool.py` — the script builds and calls `PUT <self-hosted-mcp-url>registeredDeployments/<deployment_id>` for runtime registration without a restart. (Under the hood this is a `PUT` to the path `/registeredDeployments/<deployment_id>` relative to the self-hosted MCP server's `.../directAccess/mcp/` base URL.)
2. Restart the server. It will discover all currently-tagged deployments on boot.

Option 1 is preferred in production because it avoids downtime for other registered tools.

## Feature Flag (Hosted Only)

The hosted global MCP server checks the feature flag `ENABLE_MCP_TOOLS_GALLERY_SUPPORT` before it exposes tagged deployments. If this flag is off, your tagged deployment will not appear in `tools/list` on the hosted server regardless of the tag.

You can check the current flag state at any time:

```bash
python scripts/check_tool_gallery_flag.py
```

The script calls `POST /api/v2/entitlements/evaluate/` and reports whether the flag is active. Any authenticated user can read this flag. No user has write access via the API.

**Enabling the flag:**

- *On-premises DataRobot:* An org admin can toggle `ENABLE_MCP_TOOLS_GALLERY_SUPPORT` through the admin panel.
- *Cloud DataRobot:* Contact DataRobot support and reference PBMP-7644. DataRobot enables it at the org level.

This skill cannot enable the flag for you. If you are blocked by the flag and cannot wait for enablement, use the self-hosted MCP server instead — it does not check this flag and is immediately available.

## Verify + Connect Your Client

After tagging and surfacing the tool, confirm it is reachable before configuring your client.

**Verify the tool appears in `tools/list`:**

```bash
python scripts/verify_mcp_tool.py <deployment_id> \
  --mcp-url https://<host>/api/v2/genai/globalmcp/mcp
```

For a self-hosted server, substitute the per-deployment endpoint:

```bash
python scripts/verify_mcp_tool.py <deployment_id> \
  --mcp-url https://<host>/deployments/<id>/directAccess/mcp/
```

Exit code 0 confirms the tool is live. A non-zero exit prints the actual `tools/list` response so you can see what is and is not registered.

**Emit the client config block:**

```bash
# Hosted global MCP server — one config covers all registered tools
python scripts/emit_client_config.py --host <host> --hosted

# Self-hosted — one config block per deployment
python scripts/emit_client_config.py --host <host> --self-hosted --deployment-id <deployment_id>
```

For Claude Desktop, add the printed block to `~/Library/Application Support/Claude/claude_desktop_config.json` under the `mcpServers` key (on Linux: `~/.config/claude/claude_desktop_config.json`). For Cursor, paste it into Settings > MCP. All connections use `Authorization: Bearer <DATAROBOT_API_TOKEN>` over streamable-HTTP transport — no separate credential configuration is needed beyond your existing DataRobot API token.

## Scripts

These scripts ship with this skill in its `scripts/` directory — run them from there; you do not need to write them. They require the `datarobot` SDK and `DATAROBOT_*` env vars (see Setup).

- `scripts/register_deployment_tool.py` — tags the deployment with `tool=tool` via the DataRobot Python SDK; with `--self-hosted-mcp-url <url>` also calls `PUT <url>registeredDeployments/<deployment_id>` on the self-hosted server for runtime registration without a restart.
- `scripts/check_tool_gallery_flag.py` — reads the `ENABLE_MCP_TOOLS_GALLERY_SUPPORT` feature flag from the hosted platform via `POST /api/v2/entitlements/evaluate/` and reports whether the hosted global MCP server will expose tagged deployments.
- `scripts/verify_mcp_tool.py <deployment_id> --mcp-url <url>` — sends a `tools/list` request to the specified MCP server and confirms the given deployment appears; exits non-zero with the full response if it does not.
- `scripts/emit_client_config.py --host <h> (--hosted | --self-hosted --deployment-id <id>)` — prints the MCP client configuration block (JSON) for Claude Desktop or Cursor; use `--hosted` for the platform-wide endpoint or `--self-hosted` with a deployment ID for the per-deployment endpoint.

## Related skills

- `datarobot-setup` — install the SDK, configure authentication, set env vars (run first if credentials are missing)
- `datarobot-define-tool-schema` — author the `inputSchema` for custom (non-chat) deployments before registering them
- `datarobot-deploy-nim` — deploy an NVIDIA NIM, then register it as a tool with this skill
