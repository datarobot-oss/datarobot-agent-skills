---
name: datarobot-agent-assist-build
description: >-
  Use when the user wants to design, build, code, or deploy an AI agent on DataRobot; mentions
  agent_spec.md, dress rehearsal, the DataRobot agent template, LangGraph, CrewAI, LlamaIndex, NAT,
  Base agents, MCP servers, backend APIs, custom frontends, or the DataRobot CLI.
---

# Agent Assist — Build

This skill merges **agent design, coding, and deployment** with **interactive dress-rehearsal simulation** in one place.

Assistance falls into three categories:

1. **Designing an AI agent** → Clarify requirements, build `agent_spec.md`, optionally simulate the agent before coding
2. **Coding an AI agent** → Adapt the DataRobot agent application template to the spec
3. **Deploying an AI agent** → Follow `AGENTS.md` deployment instructions

If the user's first message is simply `1`, `2`, or `3`, treat it as selecting one of these categories.

---

## On Activation

Present the three options clearly:

```
Welcome! I help you design, code, and deploy AI agents (with optional dress-rehearsal simulation before coding).

What would you like to do?
  1. Design an AI agent     → Describe your idea
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
3. **DataRobot CLI** — run `dr auth check`. If either fails, invoke the `datarobot-setup` skill before continuing. Do not print manual install instructions.
4. **Codespace** — run `python <skill_scripts_dir>/check_codespace.py` (no-op outside a Codespace). On non-zero exit, relay its message and stop; otherwise relay any exposed-ports warning it prints.

If any helper script exits with a 401 / UNAUTHORIZED error: run `dr auth login` immediately and retry the script — do not present options to the user. The scripts create `.env` automatically via `dr dotenv setup`; the only prerequisite is an authenticated CLI session.

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
     --json \
     --target-dir <target_dir>
   ```

  **CRITICAL**: In case the script fails due to any reason, do **not** proceed. Instead, return the error message to the user and ask how they want to proceed.

- Read and follow [llm-selection.md](references/llm-selection.md) to pick from the available sources (`gateway`, `litellm`, `deployed`, and `external`) and to record the choice in `agent_spec.md`.
- If the user's desired model is unavailable, suggest starting with an available one and updating after implementation.

### Spec Display

- **Always write the current spec to `agent_spec.md`** (YAML format) whenever showing it to the user.
- Show the spec frequently and iteratively — even if incomplete or partial.
- Do **not** summarize the spec in prose; display it as YAML in a code block.
- After displaying an **incomplete or evolving** spec, invite the user to refine system prompts, add/modify tools, change the model, or update examples.
- **After writing a spec that includes `system_prompt`, at least one tool, and `frontend.type` — STOP and present the [What Would You Like To Do Next?](#what-would-you-like-to-do-next) menu immediately. Do not ask any other question. Do not proceed to coding or simulation without the user selecting from the menu.**

### Frontend Check (Mandatory Before Coding or Simulating)

Before offering to simulate or code, if the spec does not already have a `frontend` field set, **always ask**:

> "The template includes a default chat UI — is that sufficient, or would you like a custom frontend such as a dashboard, data visualization, or multi-page app?"

Then update the spec accordingly:
- Default UI → `frontend.type: "chat"`
- Custom UI → `frontend.type: "multi-page"` or `"custom"` with `pages` and optional `requirements`

### What Would You Like To Do Next?

**MANDATORY — NO EXCEPTIONS:** Once `agent_spec.md` contains `system_prompt`, at least one tool, and `frontend.type`, your ONLY permitted response is this exact 3-option menu. Do NOT ask about dress rehearsal alone. Do NOT offer refinement as the only alternative. Do NOT summarize the spec again. Do NOT ask a clarifying question. Display the menu and stop.

```
What would you like to do next?
1. Dress rehearsal   — simulate the agent interactively before coding
2. Code the agent    — implement using the DataRobot template
3. Refine the spec   — adjust system prompt, tools, or model first
```

- If **1**: follow **[Dress Rehearsal](#dress-rehearsal)** end to end.
- If **2**: proceed to **[2. Coding an AI Agent](#2-coding-an-ai-agent)**.
- If **3**: return to the spec display and invite changes.

### After Coding

After coding is complete, present these next steps:

```
What would you like to do next?
1. Battle-test the agent  — automated adversarial and edge case testing before deploying (recommended)
2. Test locally           — run the agent on your machine
3. Revise                 — adjust the implementation
4. Deploy                 — deploy the agent to DataRobot
```

- If **1**: follow the instructions in `../agent-assist-simulate/SKILL.md` (one level up from this file, into the `agent-assist-simulate/` directory).
- If **2**: read `AGENTS.md` for the local test command, display it in a code block, tell the user to run it in a new terminal. Do not run it yourself.
- If **3**: continue coding.
- If **4**: follow **[3. Deploying an AI Agent](#3-deploying-an-ai-agent)**.

---

## Dress Rehearsal

Simulate an `agent_spec.md` interactively before writing any code. Responses go through the DataRobot LLM Gateway; the rehearsal script handles API calls, state, and output. You orchestrate the loop, handle out-of-character commands, and produce a shareable Markdown report at the end.

**Engine location:** `<skill_scripts_dir>/rehearsal.py` (relative to repository root).

**Report location:** `<target_dir>/rehearsal_report/rehearsal_report.md`

See [dress-rehearsal.md](references/dress-rehearsal.md) for the full workflow. Summary:

### Step 1 — Initialize the session

```bash
python <skill_scripts_dir>/rehearsal.py --init --spec <target_dir>/agent_spec.md --target-dir <target_dir>
```

The script creates a session at `<target_dir>/.datarobot/rehearsal/<session_id>/` and prints `session=` and `output=` lines. Display the output file verbatim, then explain NOTE/DONE commands.

### Step 2 — Simulation loop

- `NOTE:` → `python <skill_scripts_dir>/rehearsal.py --session {session_dir} --note "{text}"`
- User message → `python <skill_scripts_dir>/rehearsal.py --session {session_dir} "{message}"`
- `DONE` → **must run first:** `python <skill_scripts_dir>/rehearsal.py --report --session {session_dir}` (then Step 3)

Display each turn output file verbatim only.

### Step 3 — Feedback report

```bash
python <skill_scripts_dir>/rehearsal.py --report --session {session_dir}
```

Append `## Suggested Changes` to `<target_dir>/rehearsal_report/rehearsal_report.md`. If spec changes are applied, append `## Spec Updates Applied`. Tell the user the report path for sharing with QA, product, and data science.

---

## 2. Coding an AI Agent

**On Windows: coding is not supported. STOP and do NOT proceed with the next steps!**

### Before Coding Begins

Verify `agent_spec.md` contains at minimum:

- `model` — either a legacy string containing the `llm_default_model` value of a gateway entry (strings are treated as `source: gateway`) or an object with `name` and `source` (`gateway`, `litellm`, `deployed`, or `external`). A deployed object uses the `datarobot/datarobot-deployed-llm` placeholder and must include `llm_deployment_id`.
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

   e. **Validate the template**: Run `dr dependency check`. On non-zero exit:
      - Any other error — hard stop and return the full output to the user.
   f. **Setup the template**: Run the helper script. Set `<model-name>` to the legacy string `model` value or to `model.name` for an object. Set `<model-source>` to `gateway` for a legacy string or to `model.source` for an object, then pass it as `--llm-source`:
   ```
   python <skill_scripts_dir>/setup_template.py \
     --llm-model <model-name> \
     --llm-source <model-source> \
     --target-dir .
   ```

   If the spec's model object has `source: deployed`, also pass its `llm_deployment_id` — the model placeholder alone cannot route to a deployment, and the script stops if it is missing:
   ```
   python <skill_scripts_dir>/setup_template.py \
     --llm-model <model-name> \
     --llm-source deployed \
     --llm-deployment-id <deployment-id> \
     --target-dir .
   ```

   **CRITICAL**: In case any of the above scripts fail due to any reason, do **not** proceed with coding. Instead, return the error message to the user and ask how they want to proceed.

   g. **Re-read `AGENTS.md`** now that the template is ready.
4. Recreate the TODO list based on `agent_spec.md` — break down the implementation into discrete steps and add them to the TodoWrite tool.


### Coding Rules

- Implement by adapting the template code — do not write from scratch
- Modify files only inside the current directory and its subdirectories
- Do not view `.env` files (`.env.template` files are OK)
- **Tool credentials** — when implementing a tool with `auth_spec` in `agent_spec.md`:
  1. Choose a `SCREAMING_SNAKE_CASE` env var name (e.g. `PERPLEXITY_API_KEY`).
  2. **Append** `VAR_NAME=` to `<target_dir>/.env` without reading the file.
  3. Ask the user to paste the secret into `<target_dir>/.env` in their editor — never in chat, `agent_spec.md`, or committed code.
- Do not add code comments unless asked
- Do not mock tool implementations unless they would be complex to implement
- For tasks with 3+ steps, use the TodoWrite tool to manage your work
- Keep text responses **concise (1–3 sentences)** while coding — skip preamble and postamble

### File Write/Edit Discipline

- Always explain **why** the change is needed (purpose and impact) in 1–2 sentences before writing or editing a file
- Invoke at most **one shell command per response** — wait for the result before invoking another


---

## 3. Deploying an AI Agent

- Read `AGENTS.md` for deployment instructions
- Follow the instructions **strictly**
- Do not deviate without user confirmation

---

## Helper Scripts

The following are the examples of helper scripts used in the skill. They are located in the `scripts` directory and are designed to assist with various tasks.

### list_llm_models.py

Lists the LLMs available to an agent.

Fetches and displays active LLM Gateway catalog models and DataRobot text-generation deployments, each tagged with its `source`:
```bash
python <skill_scripts_dir>/list_llm_models.py \
  --json \
  --target-dir <target_dir>
```

Requires env vars: `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT`

### clone_template.py

Clones the DataRobot agent application template repository.

Clones the template to the current directory (repository URL and branch are hardcoded):
```bash
python <skill_scripts_dir>/clone_template.py
```

Clone to a specific directory:
```bash
python <skill_scripts_dir>/clone_template.py \
  --target-dir ./my-project
```

### setup_template.py

Sets up a template repository for initializing a new agent project.

```bash
python <skill_scripts_dir>/setup_template.py \
  --llm-model <model-name> \
  --llm-source <model-source> \
  --target-dir .
```

Add `--llm-source deployed` and `--llm-deployment-id <deployment-id>` for a DataRobot-deployed LLM, so the template routes to the deployment instead of the gateway.

For an external model, pass `--llm-source external`; the template reads its configured base URL and API key from the environment and writes the `EXTERNAL_LLM_*` keys.

### select_framework.py

Saves the chosen agentic framework to `.datarobot/answers/agent-agent.yml`
(field `agent_template_framework`). Preserves all other fields in the file.

```bash
python <skill_scripts_dir>/select_framework.py \
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
model:
  name: "datarobot/azure/gpt-5-2025-08-07" # the listing's llm_default_model, verbatim
  source: gateway
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
- During **coding**: keep responses to 1–3 sentences; no introductions or conclusions
- During **design**: be conversational and thorough

