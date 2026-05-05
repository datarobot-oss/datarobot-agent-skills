---
name: datarobot-mcp-server-deployment
description: MCP deploy: create missing `dr_mcp/.env` / root `.env` with skeleton then user fills; Gate, auth-check, post-deploy `list_deployments` curl; stop on failure—no secrets in chat.
---

# DataRobot MCP server deployment

**Source repo:** `git clone https://github.com/datarobot-community/datarobot-mcp-template.git` then `cd datarobot-mcp-template`. Stack is **Pulumi** + **pulumi-datarobot**; app is **FastMCP** packaged as a custom model on **DataRobot Serverless**. **Do not** use DataRobot Python SDK alone for this path—use the template and Task commands below.

## Prerequisites

Ask the user to confirm tools are installed; give install hints by OS.

| Need | Role |
|------|------|
| Python **3.11+** | `dr_mcp` and `infra` use uv-managed envs (often 3.12 in template) |
| **Task** (`task` CLI) | Taskfile at repo root |
| **uv** | Python package manager / sync |
| **Pulumi** (`pulumi` CLI) | IaC deploy to DataRobot |
| **DataRobot API token** + **endpoint** | DataRobot UI → user menu → **API keys and tools**; never paste into chat—use `.env` files |
| Optional: Docker | Container workflows in template |

**macOS (Homebrew example):** `brew install python`, `brew install go-task/tap/go-task`, `brew install uv`, `brew install pulumi/tap/pulumi`

**Linux (Debian/Ubuntu):** `sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv`; Task: `sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b ~/.local/bin`; uv: `curl -Ls https://astral.sh/uv/install.sh | sh`; Pulumi: `curl -fsSL https://get.pulumi.com | sh`

Use **`DATAROBOT_ENDPOINT` with no trailing slash**. Often set to the **API base including `/api/v2`**, e.g. `https://app.datarobot.com/api/v2` or `https://app.eu.datarobot.com/api/v2`, so Pulumi-built URLs match DataRobot (`…/api/v2/deployments/…/directAccess/mcp`). If you use only `https://app.datarobot.com`, stack URLs will omit `/api/v2`—confirm against the **verbatim** MCP output below.

## Environment files

### `dr_mcp/.env` (required before deploy)

If this file is **missing**, **create** it per **Missing `.env` files (create, then user fills)** before asking the user to fill values.

Create `dr_mcp/.env` with at least:

```bash
DATAROBOT_API_TOKEN=<user API key>
DATAROBOT_ENDPOINT=https://app.datarobot.com
SESSION_SECRET_KEY=<long random hex string>
```

Generate `SESSION_SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(64))"`

Optional keys also appear in the cloned repo’s `README.md` / `.env.template`.

```bash
# MCP_SERVER_NAME=datarobot-mcp-server
# MCP_SERVER_PORT=8080
# USE_MCP_TARGET_TYPE=true   # set false if instance lacks MCP target type
# MCP_SERVER_LOG_LEVEL=WARNING
# APP_LOG_LEVEL=INFO
```

### Repo root `.env` (required before deploy)

If this file is **missing**, **create** it per **Missing `.env` files (create, then user fills)** (or `cp dr_mcp/.env .env` after `dr_mcp/.env` exists, then add **`PULUMI_CONFIG_PASSPHRASE`**).

After `dr_mcp/.env` is valid:

```bash
cp dr_mcp/.env .env
```

Edit root `.env` and set **non-empty** `PULUMI_CONFIG_PASSPHRASE` (any strong passphrase; encrypts Pulumi secrets in stack config). If using **Pulumi Cloud** instead of local state: `pulumi login` with the user’s Pulumi account/token; `PULUMI_CONFIG_PASSPHRASE` still protects stack config secrets.

Optional at root (from template `.env.template`):

```bash
# DATAROBOT_DEFAULT_USE_CASE=<uuid>   # empty = create new use case
# USE_MCP_TARGET_TYPE=true
# DATAROBOT_DEFAULT_MCP_EXECUTION_ENVIRONMENT="[DataRobot] Python 3.11 GenAI Agents"
# DATAROBOT_DEFAULT_MCP_EXECUTION_ENVIRONMENT_VERSION_ID=<id>
# DATAROBOT_DEFAULT_PREDICTION_ENVIRONMENT=<uuid>   # reuse existing prediction env
```

Private-CA installs only: set `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE` to the org CA bundle path.

## Missing `.env` files (agent: create, then user fills)

Paths are relative to the **cloned template root** (`<template-root>`).

| File | Expected path |
|------|----------------|
| MCP app env | **`<template-root>/dr_mcp/.env`** |
| Pulumi + Task env | **`<template-root>/.env`** (repository root) |

**Agent:** if **`dr_mcp/.env`** does not exist, **create** it with this skeleton (empty values are intentional—user fills locally):

```bash
# Fill all values below (no trailing slash on DATAROBOT_ENDPOINT). UI: DataRobot → API keys and tools.
DATAROBOT_API_TOKEN=
DATAROBOT_ENDPOINT=https://app.datarobot.com/api/v2
SESSION_SECRET_KEY=
```

**Agent:** if **root `.env`** does not exist, **create** it by copying the same keys from **`dr_mcp/.env`** (after that file exists), and **append** a Pulumi line:

```bash
PULUMI_CONFIG_PASSPHRASE=
```

(If `dr_mcp/.env` was just created, root `.env` can duplicate the three DataRobot lines plus `PULUMI_CONFIG_PASSPHRASE=` in one file.)

Then **stop** the deploy path and **tell the user** exactly which file(s) you created, their **full paths**, and that they must **fill** `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT`, `SESSION_SECRET_KEY`, and `PULUMI_CONFIG_PASSPHRASE` (and optionally point them to **How to obtain values** below). **Never** ask them to paste secrets into chat.

Optional: pre-fill `SESSION_SECRET_KEY` with `python -c "import secrets; print(secrets.token_hex(64))"` in **`dr_mcp/.env`** only, then sync/copy to root `.env` if you create both—still require user for token, endpoint, and Pulumi passphrase.

## Gate (blocking)

Do not run **`task deploy`**, **`task infra:up-yes`**, or **`pulumi up`** until:

- `dr_mcp/.env` has non-empty `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT`, `SESSION_SECRET_KEY`
- Root `.env` exists with the same DataRobot vars **and** non-empty `PULUMI_CONFIG_PASSPHRASE`

If the gate fails because files or keys are missing, first follow **Missing `.env` files (create, then user fills)**—**create** missing files in **`dr_mcp/.env`** and/or **root `.env`**, then ask the user to fill values—then follow **Agent obligations: missing variables or auth failure** if keys are still blank (stop, ask user, point to files/UI—no secrets in chat).

Validate by reading/parsing files; never echo secrets. Empty API key → Pulumi errors like `Api Key cannot be an empty string`. **`task install`** and **`pulumi login`** may run before `.env` is complete.

## Auth check first (mandatory before Pulumi deploy)

From the **template repository root** (where root **`.env`** lives), **immediately after the Gate passes** and **before** `pulumi login` / stack selection / **`task deploy`** / **`task infra:up-yes`** / **`pulumi up`**:

```bash
task infra:auth-check
```

**Agent behavior**

- **If exit code is non-zero** or the output reports invalid/expired credentials: **stop**. Do not run stack init, `pulumi up`, or deploy tasks. **Ask the user** to add or fix auth in **`dr_mcp/.env`** and **root `.env`**: non-empty **`DATAROBOT_API_TOKEN`** and correct **`DATAROBOT_ENDPOINT`** (no trailing slash; often `https://<host>/api/v2`). **Where:** DataRobot UI → user menu → **API keys and tools**. **Never** ask them to paste the token in chat—only edit local files. After they confirm, run **`task infra:auth-check`** again from the template root; repeat until it succeeds or `dr` is absent (see below).
- **If `dr` is not installed:** the task prints that auth check was skipped and exits **0**. Continue the **Deploy sequence**, but a bad token can still fail at **`pulumi up`**—then **stop** and use **Agent obligations** (same file/UI guidance).

When **`dr`** is installed, deploy tasks also invoke this check internally; doing **`task infra:auth-check`** first surfaces auth problems earlier.

## Agent obligations: missing variables or auth failure

When anything below applies, **stop the deploy path immediately**. Do not retry `pulumi up`, `task deploy`, or `task infra:up-yes` in a loop. **Ask the user** to supply or fix values **outside chat** (local files only). **Never** ask them to paste API tokens or passphrases into the conversation.

### Missing `.env` files or empty required keys (before deploy)

1. **If `dr_mcp/.env` or root `.env` is missing:** follow **Missing `.env` files (create, then user fills)**—create the file(s) in the expected folders, then **ask the user** to fill the placeholders (no secrets in chat).
2. **Stop** before `task deploy`, `task infra:up-yes`, or `pulumi up` while any required value is still blank.
3. Tell the user **which variables are missing or blank** (names only, e.g. `DATAROBOT_API_TOKEN`, `PULUMI_CONFIG_PASSPHRASE`)—not their values.
4. **Where to fix**
   - **`dr_mcp/.env`** (under the cloned template root): must set `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT`, `SESSION_SECRET_KEY`.
   - **`.env`** at the **repository root** (same clone): must include the same three DataRobot-related vars **and** `PULUMI_CONFIG_PASSPHRASE`. If root `.env` is missing after `dr_mcp/.env` exists, create it per **Missing `.env` files** (or `cp dr_mcp/.env .env` then add `PULUMI_CONFIG_PASSPHRASE=`).
5. **How to obtain values**
   - **Token + endpoint:** DataRobot web UI → user/account menu → **API keys and tools** → copy **API endpoint** (no trailing slash) and create or copy an **API key**.
   - **`SESSION_SECRET_KEY`:** Run locally: `python -c "import secrets; print(secrets.token_hex(64))"` and put the output in `dr_mcp/.env`, then sync root `.env` again if needed.
   - **`PULUMI_CONFIG_PASSPHRASE`:** User-chosen strong passphrase for encrypting stack config secrets; root `.env` only.

### Auth errors (`task infra:auth-check`, `dr auth check`, invalid/expired token, 401)

Typical messages: invalid or expired `DATAROBOT_API_TOKEN`, auth check failed, `dr dotenv update`, or Pulumi/DataRobot API **401**.

1. **Stop**; do not continue deploy until the user fixes credentials.
2. Ask the user to **update root `.env`** (path: **`<template-root>/.env`**) and **`dr_mcp/.env`** so both contain the same valid `DATAROBOT_API_TOKEN` and correct `DATAROBOT_ENDPOINT`.
3. **Where:** same paths as above; **DataRobot UI** → **API keys and tools** for a new key if the old one expired.
4. If the CLI suggested it: they may run **`dr dotenv update`** from their machine (per their `dr` version) **or** edit `.env` manually—still **no secrets in chat**.
5. After they confirm files are updated, re-run **`task infra:auth-check`** from the template root (see **Auth check first**), re-check the **Gate**, then continue the **Deploy sequence**—not before.

### After the user fixes files

Re-validate the **Gate** by parsing `dr_mcp/.env` and root `.env` again, run **`task infra:auth-check`** from the template root, then continue the **Deploy sequence**.

## Preflight: DataRobot CLI (`dr`)

Deploy-related tasks (`task deploy`, `task infra:up-yes`, `task infra:refresh`, `task destroy`) **also** depend on **`task infra:auth-check`** when **`dr`** is installed. The **Auth check first** section requires the agent to run that check **manually once** after the Gate and before Pulumi deploy so failures are handled early with **Agent obligations**.

If **`dr`** is not installed, that dependency is skipped inside those tasks; the manual **`task infra:auth-check`** step will no-op with a skip message—still proceed only after the **Gate** passes.

## Deploy sequence (repository root)

1. **Clone:** `git clone https://github.com/datarobot-community/datarobot-mcp-template.git && cd datarobot-mcp-template`
2. `task install` — installs `dr_mcp` + `infra` dependencies  
3. **`.env` presence:** if **`dr_mcp/.env`** or **root `.env`** is missing, **create** them per **Missing `.env` files (create, then user fills)** and **ask the user** to fill required values before continuing.  
4. User fills **`dr_mcp/.env`**, then **`cp dr_mcp/.env .env`** (if root `.env` was not created yet) + **`PULUMI_CONFIG_PASSPHRASE`** → satisfy **Gate**  
5. **`task infra:auth-check`** — **mandatory** (see **Auth check first**). If it fails, **stop** and have the user fix auth in **`dr_mcp/.env`** and **root `.env`**; do not continue until it passes (or `dr` is absent and the task skipped).  
6. `pulumi login --local` (simple file backend) or your org’s Pulumi backend (`pulumi login`)  
7. **Stack:** `cd infra && pulumi stack init <stack-name>` **or** `pulumi stack select <stack-name>`, then **`cd ..`**. If Pulumi reports **no stack selected**, run **`task infra:select -- <stack-name>`** from the template root (Task runs commands under `infra/`).  
8. **`task deploy`** … **or** **`task infra:up-yes`** — on **auth-check** or **401** / invalid token output, **stop** and follow **Agent obligations** (do not retry until the user updates `.env` files).
9. **Post-deploy verification:** run the **MCP `list_deployments` curl** (below). If it fails, treat deploy as **not verified** until headers/token/URL are fixed.

**Destroy:** `task destroy` (runs infra destroy; **also** depends on **`auth-check`** when `dr` is present—needs a valid token). To drop an **empty** stack without destroy: `cd infra && pulumi stack rm <stack-name> --yes` (non-interactive; does not delete DataRobot resources if none were created).

**Stack / outputs:** `task infra:info` (no auth-check) or `cd infra && uv run pulumi stack output` (list all outputs). If `pulumi` says no stack selected, use step 5 / `task infra:select`.

## Finding the hosted MCP URL

After successful deploy, Pulumi stack **outputs** include an entry whose name ends with **`MCP Server MCP Endpoint`** (prefix varies with stack name). Another export ends with **`Deployment Id`**.

**Prefer the verbatim output value** for clients (read from disk/terminal, not pasted into chat with unrelated logs):

- From template root: `task infra:pulumi -- stack output '<PREFIX> MCP Server MCP Endpoint'` (quote the full key name Pulumi shows), or `cd infra && uv run pulumi stack output` after `pulumi stack select`.

Template composes the URL as `{DATAROBOT_ENDPOINT}/deployments/{DEPLOYMENT_ID}/directAccess/mcp` (no extra `/api/v2` segment in code—if your endpoint is `https://host/api/v2`, the result includes `/api/v2/deployments/…`).

**Log hygiene:** `pulumi up` may print stack outputs to the terminal, including sensitive exports (e.g. `SESSION_SECRET_KEY`). Do not paste raw deploy logs into chat; rotate credentials if logs leaked.

## Post-deploy verification (MCP `list_deployments`)

**When:** immediately after **`task deploy`** / **`task infra:up-yes`** succeeds (or any time you need to confirm the hosted MCP server is healthy).

**Agent:** run this from the user’s machine **before** declaring success. Do **not** paste `DATAROBOT_API_TOKEN` into chat—the user should **`export`** it in their shell from **root `.env`** (same value as in the file).

1. Set **`MCP_URL`** to the **verbatim** stack output **`… MCP Server MCP Endpoint`** (same as client config), e.g.  
   `task infra:pulumi -- stack output '<PREFIX> MCP Server MCP Endpoint'`
2. **`export DATAROBOT_API_TOKEN=…`** from **`<template-root>/.env`** locally (no echo in shared logs if possible).

**Why two headers:** on hosted DataRobot MCP, **`tools/call`** (including **`list_deployments`**) requires **`x-datarobot-api-token`** as well as **`Authorization: Bearer …`**. With Bearer alone, **`tools/list`** may work but **`list_deployments`** can return `[authentication] DataRobot API token not found in headers`.

```bash
curl -sS -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $DATAROBOT_API_TOKEN" \
  -H "x-datarobot-api-token: $DATAROBOT_API_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_deployments","arguments":{}}}'
```

**Success:** response is **SSE** (`event: message` / `data:` lines). In the `data:` JSON, **`result.content[0].text`** is a JSON string whose parsed object includes a **`deployments`** object (map of deployment id → label).

**Failure:** `data` JSON has **`"isError":true`**—read `result.content[0].text` (e.g. auth errors). Fix token/headers/`MCP_URL` and retry.

**Optional lighter check** (same URL and headers):

```bash
curl -sS -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $DATAROBOT_API_TOKEN" \
  -H "x-datarobot-api-token: $DATAROBOT_API_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 2000
```

Expect **`list_deployments`** among `result.tools[].name`.

## Local run

From `dr_mcp/`: `task dev` → health `http://localhost:8080/`, MCP at **`http://localhost:8080/mcp/`**. Optional: `task test-interactive` (needs LLM network for agent side).

Quick checks:

```bash
curl -s http://localhost:8080/
curl -s http://localhost:8080/mcp/
```

Token sanity (no secret in logs; user runs locally):

```bash
# When DATAROBOT_ENDPOINT is the API base including /api/v2 (recommended):
curl -s -H "Authorization: Bearer $DATAROBOT_API_TOKEN" "${DATAROBOT_ENDPOINT}/projects/?limit=1" | head -c 200
# When DATAROBOT_ENDPOINT is only the site origin (https://host):
curl -s -H "Authorization: Bearer $DATAROBOT_API_TOKEN" "${DATAROBOT_ENDPOINT}/api/v2/projects/?limit=1" | head -c 200
```

If that route is blocked on your org, use any lightweight authenticated `GET` under your API base that your role allows.

## MCP clients (hosted deployment)

Set **`YOUR_MCP_URL`** to the **full string** from the stack output **`… MCP Server MCP Endpoint`** (copy from `pulumi stack output` / `task infra:pulumi -- stack output '…'`—avoids hand-joining host + `/api/v2` + deployment id). Use **`YOUR_API_KEY`** = same `DATAROBOT_API_TOKEN` you use in `.env` (never paste into chat). On **hosted** deployments, set **`Authorization`** and **`x-datarobot-api-token`** to the same API key value so **tool calls** (including **`list_deployments`**) authenticate—the same requirement as **Post-deploy verification**.

**Cursor — local** (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "datarobot-local": {
      "url": "http://localhost:8080/mcp/"
    }
  }
}
```

**Cursor — hosted** (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "datarobot-mcp": {
      "url": "YOUR_MCP_URL",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY",
        "x-datarobot-api-token": "YOUR_API_KEY"
      }
    }
  }
}
```

**VS Code** (`mcp.json` under user settings path for OS):

```json
{
  "mcp": {
    "servers": {
      "datarobot-mcp": {
        "url": "YOUR_MCP_URL",
        "type": "http",
        "headers": {
          "Authorization": "Bearer YOUR_API_KEY",
          "x-datarobot-api-token": "YOUR_API_KEY"
        }
      }
    }
  }
}
```

**Claude Desktop** (needs Node.js): `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS; path differs on Windows/Linux)

```json
{
  "mcpServers": {
    "datarobot-mcp": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote@latest",
        "YOUR_MCP_URL",
        "--header",
        "Authorization: ${AUTH_HEADER}",
        "--header",
        "x-datarobot-api-token: ${DR_API_TOKEN}",
        "--transport",
        "http"
      ],
      "env": {
        "AUTH_HEADER": "Bearer YOUR_API_KEY",
        "DR_API_TOKEN": "YOUR_API_KEY"
      }
    }
  }
}
```

**Local client (no auth header):** URL `http://localhost:8080/mcp/` only.

After edits: fully restart Cursor / VS Code / Claude Desktop; in VS Code use “Developer: Reload Window”.

## Troubleshooting (short)

| Symptom | Check |
|---------|--------|
| Missing `.env` files | **Create** **`dr_mcp/.env`** and/or **root `.env`** per **Missing `.env` files**; **ask user** to fill placeholders — no secrets in chat |
| `task infra:auth-check` fails (non-zero) | **Stop**; user fixes **`DATAROBOT_API_TOKEN`** / **`DATAROBOT_ENDPOINT`** in **`dr_mcp/.env`** and **root `.env`** (UI: **API keys and tools**); re-run **`task infra:auth-check`** before deploy |
| Missing Gate vars or other auth / 401 | **Stop**; **Agent obligations: missing variables or auth failure** — no secret paste in chat |
| `error: no stack selected` | `task infra:select -- <stack-name>` or `cd infra && pulumi stack select <stack-name>` |
| Port 8080 in use | `lsof -i :8080` or `MCP_SERVER_PORT=8081` then `task dev` |
| Pulumi empty API key | Both `dr_mcp/.env` and root `.env` contain `DATAROBOT_API_TOKEN` |
| MCP **`tools/call`** returns `[authentication]` / token not in headers | Add **`x-datarobot-api-token`** (same value as API key) alongside **`Authorization: Bearer …`** — see **Post-deploy verification** |
| Older DataRobot without MCP model type | `USE_MCP_TARGET_TYPE=false` then redeploy |
| Tools missing in client | Restart client; check server logs for tool registration errors |
| Same stack name, different clone dirs | Pulumi **project** name is fixed in `infra/Pulumi.yaml` (`fastmcp-template`); stacks live in the configured backend—pick **unique stack names** if you reuse `pulumi login --local` |

## Commands reference

| Action | Command |
|--------|---------|
| Install | `task install` |
| Auth preflight (run first after Gate) | `task infra:auth-check` |
| Local MCP | `cd dr_mcp && task dev` |
| Deploy | `task deploy` or `task infra:up-yes` |
| Stack | `task infra:info` |
| Select stack | `task infra:select -- <name>` |
| Verify hosted MCP (`list_deployments`) | See **Post-deploy verification** (`curl` + `tools/call`) |
