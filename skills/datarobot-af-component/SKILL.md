---
name: datarobot-af-component
description: >-
  EXPERIMENTAL — invoke-only during initial testing. Use when the user explicitly
  invokes /datarobot-af-component to discover, inspect, or compose DataRobot
  Application Framework v2 components via `dr component`. Do not auto-activate
  from natural-language triggers about agents, AF, or MCP.
---

# AF Component

A lean, spec-free skill for working with the AF v2 component registry via the DataRobot CLI.

Focused purely on the `dr component` CLI loop. No `agent_spec.md` dependency, no design phase, no coding phase. Use this when you know what you want to build and need help discovering, inspecting, and composing AF components.

---

## Script Path Resolution

Before invoking any helper script, resolve `<skill_scripts_dir>` once for the session:

- `<skill_scripts_dir>` is the `scripts/` subdirectory of the directory containing this `SKILL.md` file.
- Confirm it exists with `ls <path_to_this_skill_dir>/scripts/`. If the directory is missing, tell the user the skill installation is incomplete and stop.
- Use the resolved absolute path for every `<skill_scripts_dir>/...` reference in this skill.

---

## Pre-requisite Check

Run in order before proceeding with any flow:

1. **Git** — run `git --version`. If missing, tell the user to install from https://git-scm.com and stop.
2. **Python** — run `python --version`. If missing or below 3.11, tell the user to install Python 3.11+ from https://python.org and stop.
3. **DataRobot CLI** — follow **DataRobot CLI Setup** at the bottom:
   - If missing, **ALWAYS RUN** the install command before proceeding.
   - **ALWAYS RUN** the upgrade command before proceeding.
   - If not authenticated, **ALWAYS RUN** the auth command before proceeding.

---

## Three Flows

### 1. Discover

```bash
dr component list-available --format json
```

Present the component list with `agent_guidance.summary` for each. Mark repeatable components. Let the user identify which modules they want.

### 2. Inspect

```bash
dr component describe <module> --format json
```

For each module: display name, description, dependencies, all questions with type/default/help, and `agent_guidance` per question (`ask_user`, `reason`).

### 3. Compose

Guided sequence — no external spec file required:

1. **Identify modules** — from user input or the output of Discover.
2. **Describe each module** — run `dr component describe <module> --format json` for each. Collect all questions; deduplicate by name across modules.
3. **Partition questions**:
   - `ask_user: true` — ask the user (show `help` and `reason`)
   - `ask_user: false` — derive silently using the derivation map below
4. **STOP. Do NOT run `compose_template.py` until all `ask_user: true` questions have been answered.**
5. **Run `compose_template.py`** with the pre-collected answers.

#### Derivation map for `ask_user: false` questions

| Question name | Derivation |
|---|---|
| `agent_app_name`, `llm_app_name` | Slugify working directory name |
| `mcp_app_name` | `mcp_server` |
| `copyright_year` | Current year |
| `mcp_development_port` | `8080` |
| All others | Declared default |

#### compose_template.py invocation

```bash
python <skill_scripts_dir>/compose_template.py \
  --modules '<json array>' \
  --answers '<json object of label.question=value>' \
  --target-dir .
```

Pass `--registry-uri file://...` if the registry is not yet live.

**CRITICAL**: On failure, do **not** proceed. Return the full error to the user. If the error mentions a missing registry or component, advise the user to pass `--registry-uri file://...` pointing at a local registry.

---

## Error Handling

- If a tool returns an error, read the error message carefully before responding.
- For template-prep **warnings**: try to resolve yourself.
- For template-prep **errors**: return the message to the user and ask how to proceed.
- On unexpected errors, ask the user if they want to retry.

---

## DataRobot CLI Setup

The DataRobot CLI (`dr`) is required for managing DataRobot custom applications.

### Verify Installation

Check if the CLI is installed:

```bash
dr --version
```

Expected output: `DataRobot CLI version: v0.2.66` (or similar)

### Install DataRobot CLI

If not installed, run:

**macOS/Linux:**
```bash
curl https://cli.datarobot.com/install | sh
```

**Windows:**
```powershell
irm https://cli.datarobot.com/winstall | iex
```

### Upgrade CLI

If the CLI version is too old, run to upgrade:

```bash
dr self update --force
```

### Check Authentication Status

Verify the CLI is authenticated:

```bash
dr auth check
```

### Authenticate

If not authenticated, run:

```bash
dr auth login
```

This will guide the user through the authentication process interactively.
