---
name: datarobot-agent-assist
description: >-
  Use when the user wants to design, build, code, simulate, or deploy an AI agent (not a predictive
  model) to DataRobot; mentions agent_spec.md, dr-assist, datarobot-agent-assist, dress rehearsal,
  or the DataRobot agent template; wants to scaffold a LangGraph, CrewAI, LlamaIndex, NAT, or Base
  agent targeting DataRobot; wants to add an MCP server, backend API, or React frontend to a
  DataRobot agent application; or uses the DataRobot CLI (dr) to build or deploy an agentic custom
  application. Covers the full workflow: agent design, agent_spec.md authoring, dress-rehearsal
  simulation via the DataRobot LLM Gateway, template-based coding, and deployment.
---

# DataRobot Agent Assist

This skill merges **agent design, coding, and deployment** with an optional **dress-rehearsal simulation** — a try-before-you-build session that lets you chat with your agent design before writing any code.

Assistance falls into three categories:

1. **Designing an AI agent** → Clarify requirements, build `agent_spec.md`, optionally simulate the agent before coding
2. **Coding an AI agent** → Adapt the DataRobot agent application template to the spec
3. **Deploying an AI agent** → Follow `AGENTS.md` deployment instructions

If the user's first message is simply `1`, `2`, or `3`, treat it as selecting one of these categories.

---

## On Activation

Present the three options clearly:

```
Welcome! I help you design, code, and deploy AI agents.

What would you like to do?
  1. Design an AI agent     → Describe your idea (optional dress rehearsal before coding)
  2. Code an AI agent       → Load and implement an existing agent_spec.md
  3. Deploy an AI agent     → Deploy an implemented agent to DataRobot
```

Show this menu first. After the user selects an option (`1`, `2`, or `3`), run the **[Pre-requisite Check](#pre-requisite-check)** and then the **[Script Path Resolution](#script-path-resolution)**.

- Options **1** and **2** — read and follow [references/workspace-resolution.md](references/workspace-resolution.md), then proceed to the selected workflow.
- Option **3** — skip Workspace Resolution; `<target_dir>` is resolved in the [Pre-deployment Checklist](references/pre-deployment-checklist.md) when unset.

---

## Script Path Resolution

Before invoking any helper script, resolve `<skill_scripts_dir>` once for the session:

- `<skill_scripts_dir>` is the `scripts/` subdirectory of the directory containing this `SKILL.md` file.
- Confirm it exists with `ls <path_to_this_skill_dir>/scripts/`. If the directory is missing, tell the user the skill installation is incomplete and stop.
- Use the resolved absolute path for every `<skill_scripts_dir>/...` reference in this skill.

---

## Session State

Track these for the conversation:

- `<target_dir>` — project root for design, coding, and deployment. Set during [Workspace Resolution](references/workspace-resolution.md) or the [Pre-deployment Checklist](references/pre-deployment-checklist.md). Reuse across phases in the same session. Only change when the user explicitly asks, during [pre-coding subdir recovery](references/pre-coding-checklist.md), or in a new session.
- `<dependency_check_passed>` — `false` until a passing `dr dependency check` in `<target_dir>`.
- `<dependency_check_target_dir>` — the `<target_dir>` value when the last check passed.

### Dependency check session rule

Before running `dr dependency check`:

- If `<dependency_check_passed>` is true and `<target_dir>` equals `<dependency_check_target_dir>`, skip the check.
- Otherwise, run `dr dependency check` in `<target_dir>`. On zero exit: set `<dependency_check_passed>` = true and `<dependency_check_target_dir>` = `<target_dir>`. On non-zero exit: hard stop — return full output; do not attempt to resolve automatically.

Invalidate `<dependency_check_passed>` (set to false) when:

- `<target_dir>` changes
- `clone_template.py`, `select_framework.py`, or `setup_template.py` runs in `<target_dir>`

---

## Workspace Resolution

Read and follow [references/workspace-resolution.md](references/workspace-resolution.md) after menu options **1** or **2**.

---

## Pre-requisite Check

Run in order before proceeding:

1. **Git** — run `git --version`. If missing, tell the user to install from https://git-scm.com and stop.
2. **Python** — run `python --version`. If missing or below 3.11, tell the user to install Python 3.11+ from https://python.org and stop.
3. **DataRobot CLI** — follow **DataRobot CLI Setup** at the bottom:
   - If missing, **ALWAYS RUN** the install command before proceeding
   - **ALWAYS RUN** the upgrade command before proceeding
   - If not authenticated, **ALWAYS RUN** the auth command before proceeding

---

## 1. Designing an AI Agent

### Clarification Phase

- Ask **at most 2 rounds** of clarifying questions before proposing an initial draft spec. If tools are still ambiguous after two rounds, start simple.
- Focus questions on:
  - What the agent does and who uses it
  - What tools it needs and what external services those tools call
  - Whether those services require authentication (API key, OAuth2, bearer token, etc.)
  - Whether the user needs a custom frontend beyond the default chat UI

- If the user mentions UI-related needs early ("dashboard", "visualization", "multi-page", "admin panel", "settings page"), capture it immediately in the `frontend` field — do **not** defer.

### Model Selection

- To check available models, run the helper script from `<target_dir>`:
   ```
   python <skill_scripts_dir>/list_llm_models.py \
     --json
   ```

  **CRITICAL**: In case the script fails due to any reason, do **not** proceed. Instead, return the error message to the user and ask how they want to proceed.

- Recommend a `gpt-5`, `claude-4-5`, or `gemini-2.5` model from the list unless the user specifies cost or other constraints.
- If none of those preferred families appear in the catalog, pick the highest-capability available model by name — prefer ones containing `large`, `pro`, `opus`, or `sonnet` over `mini`, `haiku`, or `flash`.
- Only display the full model catalog when the user **explicitly** asks to browse models.
- If the user's desired model is unavailable, suggest starting with an available one and updating after implementation.

### Spec Display

- **Always write the current spec to `<target_dir>/agent_spec.md`** (YAML format) whenever showing it to the user.
- Show the spec frequently and iteratively — even if incomplete or partial.
- Do **not** summarize the spec in prose; display it as YAML in a code block.
- After displaying, invite the user to refine system prompts, add/modify tools, change the model, or update examples.

### Frontend Check (Mandatory Before Coding or Simulating)

Before offering to simulate or code, if the spec does not already have a `frontend` field set, **always ask**:

> "The template includes a default chat UI — is that sufficient, or would you like a custom frontend such as a dashboard, data visualization, or multi-page app?"

Then update the spec accordingly:
- Default UI → `frontend.type: "chat"`
- Custom UI → `frontend.type: "multi-page"` or `"custom"` with `pages` and optional `requirements`

### Agent Simulation (Before Coding)

Before transitioning to coding, explain dress rehearsal briefly, then ask (exact wording):

> **Dress rehearsal** is a try-before-you-build session: you chat with your agent design as if it were already running. The agent uses your spec's model and system prompt; tool calls return **simulated** (fake but realistic) data — no real APIs, no deployment, no code written yet. It's a safe way to test prompts, tools, and conversation flow before implementation.
>
> Would you like to run a dress rehearsal simulation first? (recommended)

Wait for their reply:

- **If yes** — follow **[Dress Rehearsal](#dress-rehearsal)** end to end. Do not substitute improvised role-play or manual mock tool traces.
- **If no** (or any decline such as "no", "skip", "not now") — go to **[Post-design next steps](#post-design-next-steps)**. **Do not** jump to coding, framework selection, or template setup.

Script path: `python <skill_scripts_dir>/rehearsal.py ...` (run from `<target_dir>`; use `--spec <target_dir>/agent_spec.md` if needed)

### Post-design next steps

After the user declines the initial rehearsal prompt — or after a dress rehearsal session ends — present this menu (exact wording):

> What would you like to do next?
> 1. **Run dress rehearsal** — simulate the agent before coding
> 2. **Code the agent** — start implementation from `agent_spec.md`
> 3. **Review / edit spec** — refine `agent_spec.md`

Wait for their choice. **Do not** assume a default or proceed without a reply.

| Choice | Action |
|--------|--------|
| 1 or "rehearsal" / "simulate" | Follow **[Dress Rehearsal](#dress-rehearsal)** |
| 2 or "code" / "implement" | Follow **[2. Coding an AI Agent](#2-coding-an-ai-agent)** — read and follow [references/pre-coding-checklist.md](references/pre-coding-checklist.md) |
| 3 or "review" / "edit spec" | Display `<target_dir>/agent_spec.md` as YAML, invite changes, update the file, then show this menu again |

If the user's reply is unclear, re-display the menu and wait. Never skip straight to framework selection after a rehearsal decline.

---

## Dress Rehearsal

Before running rehearsal, read and follow `references/dress-rehearsal.md` end to end.

**Mandatory:**
- Run the engine from this skill: `python <skill_scripts_dir>/rehearsal.py ...`
- Preserve all exact prompts/menu text and turn-handling rules from `references/dress-rehearsal.md`
- During rehearsal turns, display only the script output file contents
- After rehearsal ends, produce the required report format, then return to **[Post-design next steps](#post-design-next-steps)**

---

## 2. Coding an AI Agent

**On Windows: coding is not supported. STOP and do NOT proceed with the next steps!**

### Before Coding Begins

Verify `<target_dir>/agent_spec.md` contains at minimum:

- `model` — a valid LLM Gateway model ID
- `system_prompt` — non-empty
- `tools` — at least one tool defined (or explicit confirmation from the user that no tools are needed)
- `frontend.type` — set

If `agent_spec.md` does not exist in `<target_dir>`, inform the user and offer to run the Design phase (option 1) first. If any required field above is missing, surface the gap and update the spec before continuing. Do not start coding against an incomplete spec.

### Pre-coding Checklist

Read and follow [references/pre-coding-checklist.md](references/pre-coding-checklist.md) end to end before writing or editing implementation code.

### Coding Rules

- Implement by adapting the template code — do not write from scratch
- Modify files only inside `<target_dir>` and its subdirectories
- Do not view `.env` files (`.env.template` files are OK)
- Do not add code comments unless asked
- Do not mock tool implementations unless they would be complex to implement
- For tasks with 3+ steps, use the TodoWrite tool to manage your work
- Keep text responses **concise (1–3 sentences)** while coding — skip preamble and postamble

### File Write/Edit Discipline

- Always explain **why** the change is needed (purpose and impact) in 1–2 sentences before writing or editing a file
- Invoke at most **one shell command per response** — wait for the result before invoking another

### After Coding

1. Read `<target_dir>/AGENTS.md` to find the local test command.
2. Display the command in a code block.
3. Tell the user: "Run this command in a **new terminal** in `<target_dir>` to test the agent locally."
4. Do **not** run the command yourself.
5. Present next steps: revise the implementation, or deploy to DataRobot (follow [references/pre-deployment-checklist.md](references/pre-deployment-checklist.md)).

---

## 3. Deploying an AI Agent

Read and follow [references/pre-deployment-checklist.md](references/pre-deployment-checklist.md) end to end.

If the user requests deploy in the same session without having coded, explain that implementation is required and offer **[2. Coding an AI Agent](#2-coding-an-ai-agent)**.

---

## Helper Scripts

The following are the examples of helper scripts used in the skill. They are located in the `scripts` directory and are designed to assist with various tasks.

### list_llm_models.py

Lists available LLM models from DataRobot LLM Gateway.

Fetches and displays active models from the DataRobot LLM Gateway catalog:
```bash
python <scripts_dir>/list_llm_models.py \
  --json
```

Requires env vars: `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT`

### clone_template.py

Clones the DataRobot agent application template repository.

Clones the template to a target directory (repository URL and tag are defined in the script):
```bash
python <scripts_dir>/clone_template.py \
  --target-dir <target_dir>
```

The canonical template URL is the `REPO_URL` constant in this script — reference it for remote comparison; do not hardcode the URL elsewhere.

### setup_template.py

Sets up a template repository for initializing a new agent project.

```bash
python <scripts_dir>/setup_template.py \
  --llm-model <model-name> \
  --target-dir <target_dir>
```

### select_framework.py

Saves the chosen agentic framework to `.datarobot/answers/agent-agent.yml`
(field `agent_template_framework`). Preserves all other fields in the file.

```bash
python <scripts_dir>/select_framework.py \
  --framework langgraph \
  --target-dir <target_dir>
```

Valid `--framework` values: `langgraph`, `crewai`, `llamaindex`, `nat`, `base`


## Error Handling

- If a tool returns an error, read the error message carefully before responding
- For template-prep **warnings**: try to resolve yourself
- For template-prep **errors**: return the message to the user and ask how to proceed
- For `dr dependency check` failures: hard stop — return full output; do not attempt to resolve automatically (see [Dependency check session rule](#dependency-check-session-rule))
- On unexpected errors, ask the user if they want to retry

---

## agent_spec.md Schema

Write specs in YAML to `<target_dir>/agent_spec.md`. Fields are optional when the spec is still evolving.

```yaml
model: "anthropic/claude-sonnet-4-5-20250929"   # DataRobot LLM Gateway model ID
system_prompt: "Your agent's instructions..."
tools:
  - function_name: tool_name
    inputs:
      - arg_name: input_arg
        type: str         # one of: str, int, float, bool, list, dict
        object_schema: "(optional: schema of dict/list contents)"
    out:
      - arg_name: output_arg
        type: str
    auth_spec:
      service_name: "External API Service"
      auth_method: api_key   # api_key | oauth2 | basic_auth | bearer_token | service_account | other
examples:
  - "Example user query 1"
  - "Example user query 2"
frontend:
  type: "chat"              # chat | multi-page | custom
  pages:
    - "Analytics - shows search history and top topics"
  requirements: "(optional additional UI requirements)"
```

When tools require external service auth, note that credentials must be configured as **runtime parameters** in the infrastructure code (see `AGENTS.md` for the pattern).

See [references/agent-spec-examples.md](references/agent-spec-examples.md) for complete working examples.

---

## Tool/Helper Scripts Timeouts

- Allow up to 10 minutes for any helper script to complete before timing out and returning an error
- Allow up to 5 minutes for any tool to return a response before timing out and returning an error
- Allow up to 30 minutes for deployment-related shell commands to complete before timing out and returning an error

---


## Tool Mapping

Claude's built-in tools replace the plugin's custom Python tools:

| Plugin Tool | Claude Tool |
|---|---|
| `read_file` | Read |
| `write_file` | Write |
| `edit_file` | Edit |
| `shell` | Bash |
| `list_dir` | Glob or Bash (`ls`) |
| `grep_files` | Grep |
| `glob` | Glob |
| `web_search` | WebSearch |
| `get_web_page` | WebFetch |
| `write_todos` / `read_todos` | TodoWrite |
| `show_agent_spec` | Write to `<target_dir>/agent_spec.md` + display as YAML |
| `prepare_to_code` | Bash (`git clone` + `dr start`) |
| `list_available_models` | WebFetch (DataRobot API) |
| `code_research` | Agent (Explore subagent) |
| Agent simulation (dress rehearsal) | [Dress Rehearsal](#dress-rehearsal) + `<skill_scripts_dir>/rehearsal.py` in this skill directory |

---

## Behavioral Rules

- If it is unclear whether the request falls into one of the three categories, ask a clarifying question
- If the user insists on a task outside these three categories, politely decline
- If a user asks to code before designing, strongly encourage designing first
- If a user requests deploy without coding in the same session, offer coding — do not deploy
- Before running any CLI command or helper script, provide a clear explanation in 2-5 sentences. The explanation must include why this specific command is needed now, what it will check/change/create.
- After the user declines dress rehearsal, always show **[Post-design next steps](#post-design-next-steps)** — never skip to framework selection or the pre-coding checklist
- During **rehearsal turns**: display only the `output_file` contents — never add performance commentary or replace the script's bottom decoration / DONE hint
- During **coding**: keep responses to 1–3 sentences; no introductions or conclusions
- During **design**: be conversational and thorough

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
