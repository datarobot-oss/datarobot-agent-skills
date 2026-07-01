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

Show this menu first. After the user selects an option (`1`, `2`, or `3`), run the **[Pre-requisite Check](#pre-requisite-check)** and then the **[Script Path Resolution](#script-path-resolution)** before doing anything else for that option.

---

## Script Path Resolution

Before invoking any helper script, resolve `<skill_scripts_dir>` once for the session:

- `<skill_scripts_dir>` is the `scripts/` subdirectory of the directory containing this `SKILL.md` file.
- Confirm it exists with `ls <path_to_this_skill_dir>/scripts/`. If the directory is missing, tell the user the skill installation is incomplete and stop.
- Use the resolved absolute path for every `<skill_scripts_dir>/...` reference in this skill.

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

- To check available models: Run the helper script:
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

- **Always write the current spec to `agent_spec.md`** (YAML format) whenever showing it to the user.
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

Script path: `python <skill_scripts_dir>/rehearsal.py ...`

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
| 2 or "code" / "implement" | Follow **[2. Coding an AI Agent](#2-coding-an-ai-agent)** — framework selection happens only inside the pre-coding checklist, not here |
| 3 or "review" / "edit spec" | Display `agent_spec.md` as YAML, invite changes, update the file, then show this menu again |

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

Verify `agent_spec.md` contains at minimum:

- `model` — a valid LLM Gateway model ID
- `system_prompt` — non-empty
- `tools` — at least one tool defined (or explicit confirmation from the user that no tools are needed)
- `frontend.type` — set

If `agent_spec.md` does not exist, inform the user and offer to run the Design phase (option 1) first. If any required field above is missing, surface the gap and update the spec before continuing. Do not start coding against an incomplete spec.

### Pre-coding Checklist

1. **Read `agent_spec.md`** — it must exist (see gate above).
2. Check if `AGENTS.md` exists in the template directory (default: current working directory).
3. If `AGENTS.md` does **not** exist, prepare the template with these steps in order. ALWAYS follow the steps in order and do not skip any, even if they seem redundant. This is critical for ensuring the template is properly set up and avoiding wasted effort coding on a broken foundation.
   a. **Check the working directory** — if it contains files other than `agent_spec.md`, warn the user and ask them to clear it before proceeding.
   b. **Move `agent_spec.md` aside if present** — if the file exists in the working directory, move it to a temp location (e.g. `/tmp/agent_spec.md.bak`) before cloning so it isn't overwritten. Restore it after cloning completes.
   c. **Clone the template**: Run the helper script:
   ```
   python <skill_scripts_dir>/clone_template.py
   ```
   d. **Select the agentic framework**:

   **STOP. Do NOT proceed until the user has replied with their framework choice.**

   Ask the user (exact message):
   > Which agentic framework would you like to use?
   > 1. LangGraph
   > 2. CrewAI
   > 3. LlamaIndex
   > 4. NeMo Agent Toolkit (NAT)
   > 5. Base

   Wait for the user's reply. Do not assume or default to any framework. If their next message is not a framework choice (silence, unrelated text), re-display the options and wait again — do not proceed with any other coding step. Once the user replies, map their choice to the corresponding value (`langgraph`, `crewai`, `llamaindex`, `nat`, `base`) and run:
   ```
   python <skill_scripts_dir>/select_framework.py \
     --target-dir . \
     --framework <value>
   ```

   e. **Validate the template**: Run `dr dependency check`. Treat any non-zero exit as a hard error — do not attempt to resolve it automatically. Return the full output to the user and stop.
   f. **Setup the template**: Run the helper script. Use the `model` field from `agent_spec.md` as `--llm-model`; if absent, use the model selected during the design phase.
   ```
   python <skill_scripts_dir>/setup_template.py \
     --llm-model <model-name> \
     --target-dir .
   ```

   **CRITICAL**: In case any of the above scripts fail due to any reason, do **not** proceed with coding. Instead, return the error message to the user and ask how they want to proceed.

   g. **Re-read `AGENTS.md`** now that the template is ready.
4. Recreate the TODO list based on `agent_spec.md` — break down the implementation into discrete steps and add them to the TodoWrite tool.


### Coding Rules

- Implement by adapting the template code — do not write from scratch
- Modify files only inside the current directory and its subdirectories
- Do not view `.env` files (`.env.template` files are OK)
- Do not add code comments unless asked
- Do not mock tool implementations unless they would be complex to implement
- For tasks with 3+ steps, use the TodoWrite tool to manage your work
- Keep text responses **concise (1–3 sentences)** while coding — skip preamble and postamble

### File Write/Edit Discipline

- Always explain **why** the change is needed (purpose and impact) in 1–2 sentences before writing or editing a file
- Invoke at most **one shell command per response** — wait for the result before invoking another

### After Coding

1. Read `AGENTS.md` to find the local test command.
2. Display the command in a code block.
3. Tell the user: "Run this command in a **new terminal** in the current directory to test the agent locally."
4. Do **not** run the command yourself.
5. Present next steps: revise the implementation, or deploy to DataRobot.

---

## 3. Deploying an AI Agent

- Read `AGENTS.md` for deployment instructions
- Follow the instructions **strictly**
- Do not deviate without user confirmation

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

Clones the template to the current directory (repository URL and branch are hardcoded):
```bash
python <scripts_dir>/clone_template.py
```

Clone to a specific directory:
```bash
python <scripts_dir>/clone_template.py \
  --target-dir ./my-project
```

### setup_template.py

Sets up a template repository for initializing a new agent project.

```bash
python <scripts_dir>/setup_template.py \
  --llm-model <model-name> \
  --target-dir .
```

### select_framework.py

Saves the chosen agentic framework to `.datarobot/answers/agent-agent.yml`
(field `agent_template_framework`). Preserves all other fields in the file.

```bash
python <scripts_dir>/select_framework.py \
  --framework langgraph \
  --target-dir .
```

Valid `--framework` values: `langgraph`, `crewai`, `llamaindex`, `nat`, `base`


## Error Handling

- If a tool returns an error, read the error message carefully before responding
- For template-prep **warnings**: try to resolve yourself
- For template-prep **errors**: return the message to the user and ask how to proceed
- On unexpected errors, ask the user if they want to retry

---

## agent_spec.md Schema

Write specs in YAML to `agent_spec.md` in the working directory. Fields are optional when the spec is still evolving.

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
| `show_agent_spec` | Write to `agent_spec.md` + display as YAML |
| `prepare_to_code` | Bash (`git clone` + `dr start`) |
| `list_available_models` | WebFetch (DataRobot API) |
| `code_research` | Agent (Explore subagent) |
| Agent simulation (dress rehearsal) | [Dress Rehearsal](#dress-rehearsal) + `<skill_scripts_dir>/rehearsal.py` in this skill directory |

---

## Behavioral Rules

- If it is unclear whether the request falls into one of the three categories, ask a clarifying question
- If the user insists on a task outside these three categories, politely decline
- If a user asks to code before designing, strongly encourage designing first
- After the user declines dress rehearsal, always show **[Post-design next steps](#post-design-next-steps)** — never skip to framework selection
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
