---
name: datarobot-agent-assist
description: >-
  Use when the user wants to design, build, code, simulate, or deploy an AI agent (not a predictive
  model) to DataRobot; mentions agent_spec.md, dr-assist, datarobot-agent-assist, dress rehearsal,
  swarm simulation, or the DataRobot agent template; wants to scaffold a LangGraph, CrewAI, LlamaIndex, NAT, or Base
  agent targeting DataRobot; wants to add an MCP server, backend API, or React frontend to a
  DataRobot agent application; or uses the DataRobot CLI (dr) to build or deploy an agentic custom
  application; or wants to harden, stress-test, or battle-test an agent. Covers the full workflow: agent design, agent_spec.md authoring, dress-rehearsal
  simulation via the DataRobot LLM Gateway, adversarial swarm simulation, template-based coding, and deployment.
---

# DataRobot Agent Assist

This skill covers **agent design, coding, battle-testing, and deployment** with an optional **dress-rehearsal simulation** before any code is written.

A first message of `1`–`4` selects the corresponding category. If free text clearly maps to one category (e.g. "I want to build an agent" → Design), state the inference briefly and proceed. If ambiguous, ask which option applies — do not guess.

---

## Workflow Discipline

Follow this skill **sequentially**. These rules apply to every phase — design, coding, deployment, and every referenced checklist.

1. **Section order** — Complete each section and subsection in the order it appears in this file. Do not jump to a later section until the current one is finished.
2. **Reference files** — When this skill says **read and follow** a file under `agent-assist-build/references/`, read that file first, then execute every step in that file in order. Do not substitute a summary, shortcut, or a later menu for steps defined in the reference.
3. **Explicit skips only** — Skip a step only when this skill or the referenced file explicitly says to skip it (e.g. Pre-requisite Check when `<prerequisites_passed>` is true, or Frontend Check when `frontend.type` is already set).
4. **No auto-advance** — Completing one step (e.g. writing the spec, the user saying "move on", or a command succeeding) does not authorize skipping remaining steps. Proceed only when the current section or reference directs you to the next step.
5. **Menus and prompts** — When a section presents a menu or asks a question, wait for the user's reply. Do not assume a default or proceed on your own.
6. **One design gate per turn** — During design, do not combine prompts from different subsections in one message (e.g. do not ask about spec refinement and dress rehearsal in the same turn).

---

## On Activation

Present the four options clearly:

```
Welcome! I help you design, code, battle-test, and deploy AI agents.

What would you like to do?
  1. Design an AI agent     → Describe your idea (optional dress rehearsal before coding)
  2. Code an AI agent       → Load and implement an existing agent_spec.md
  3. Battle-test the agent  → Run adversarial swarm simulation on an implemented agent
  4. Deploy                 → Deploy an implemented agent to DataRobot
```

Show this menu first. After the user selects an option (`1`, `2`, `3`, or `4`), run the **[Pre-requisite Check](#pre-requisite-check)** (once per session) and then the **[Script Path Resolution](#script-path-resolution)**.

- Options **1** and **2** — read and follow [agent-assist-build/references/workspace-resolution.md](agent-assist-build/references/workspace-resolution.md), then proceed to the selected workflow.
- Option **3** — read `agent-assist-simulate/SKILL.md` and jump to **Pre-flight Check** (Pre-requisite Check and Script Path Resolution still apply first).
- Option **4** — skip Workspace Resolution; `<target_dir>` is resolved in the [Pre-deployment Checklist](agent-assist-build/references/pre-deployment-checklist.md) when unset.

---

## Script Path Resolution

Before invoking any helper script, resolve `<skill_scripts_dir>` once for the session:

- `<skill_scripts_dir>` is the `agent-assist-build/scripts/` subdirectory of the directory containing this `SKILL.md` file.
- Confirm it exists with `ls <path_to_this_skill_dir>/agent-assist-build/scripts/`. If the directory is missing, tell the user the skill installation is incomplete and stop.
- Use the resolved absolute path for every `<skill_scripts_dir>/...` reference in this skill.

---

## Session State

Track these for the conversation:

- `<target_dir>` — project root. Set during [Workspace Resolution](agent-assist-build/references/workspace-resolution.md) or the [Pre-deployment Checklist](agent-assist-build/references/pre-deployment-checklist.md). Reuse across phases. Change only on explicit user request, [pre-coding Bootstrap step 2](agent-assist-build/references/pre-coding-checklist.md) (spec path recovery), [pre-coding step 7](agent-assist-build/references/pre-coding-checklist.md) (subdir recovery), or a new session.
- `<prerequisites_passed>` — `false` until the [Pre-requisite Check](#pre-requisite-check) completes successfully once this session.
- `<workspace_resolved>` — `false` until [Workspace Resolution](agent-assist-build/references/workspace-resolution.md) completes for menu options **1** or **2**.
- `<workspace_resolved_target_dir>` — the `<target_dir>` set when workspace resolution last completed.
- `<design_to_code>` — `false` until the user chooses **Code the agent** from [Post-design next steps](#post-design-next-steps) in the same session after design.
- `<design_messy_cwd>` — `false` until design runs in cwd with files other than `agent_spec.md` / `.env` (see [workspace-resolution](agent-assist-build/references/workspace-resolution.md)).
- `<dependency_check_passed>` — `false` until a passing `dr dependency check` in `<target_dir>`.
- `<dependency_check_target_dir>` — the `<target_dir>` value when the last check passed.

### `.env` placement

Project credentials and config live **only** at `<target_dir>/.env` — never in cwd when `<target_dir>` is a subdirectory. This includes DataRobot CLI credentials, LLM config, and **tool/service secrets**. Pulumi reads these from the environment at deploy time (`os.environ`); a secret missing from `.env` means the corresponding credential and runtime parameter are not created.

- Complete [Workspace Resolution](agent-assist-build/references/workspace-resolution.md) before any step that needs credentials or creates a `.env` file.
- Always pass `--target-dir <target_dir>` to helper scripts that read or create `.env` (`list_llm_models.py`, `rehearsal.py`, `setup_template.py`). Do **not** run `dr dotenv setup` in cwd.
- Never put secret values in `agent_spec.md` or source code — only env var **names** belong in infra; values stay in `.env`.

### Dependency check session rule

Before running dependency validation:

- If `<dependency_check_passed>` is true and `<target_dir>` equals `<dependency_check_target_dir>`, skip validation.
- Otherwise, read and follow [agent-assist-build/references/dependency-validation.md](agent-assist-build/references/dependency-validation.md) in `<target_dir>`.

Invalidate `<dependency_check_passed>` (set to false) when:

- `<target_dir>` changes
- `clone_template.py`, `select_framework.py`, or `setup_template.py` runs in `<target_dir>`

### Welcome menu reset

When showing the [welcome menu](#on-activation) again (e.g. user declined pre-coding step 7): set `<workspace_resolved>` = false, clear `<workspace_resolved_target_dir>`, `<design_to_code>` = false, and `<design_messy_cwd>` = false. Keep `<prerequisites_passed>` true.

---

## Workspace Resolution

Read and follow [agent-assist-build/references/workspace-resolution.md](agent-assist-build/references/workspace-resolution.md) after menu options **1** or **2**.

---

## Pre-requisite Check

If `<prerequisites_passed>` is true, skip this section.

Otherwise, run in order before proceeding:

1. **Git** — run `git --version`. If missing, tell the user to install from https://git-scm.com and stop.
2. **Python** — run `python --version`. If missing or below 3.11, tell the user to install Python 3.11+ from https://python.org and stop.
3. **DataRobot CLI** — read and follow [agent-assist-build/references/dr-cli-setup.md](agent-assist-build/references/dr-cli-setup.md):
   - If missing, **ALWAYS RUN** the install command before proceeding
   - **ALWAYS RUN** the upgrade command before proceeding
   - If not authenticated, **ALWAYS RUN** the auth command before proceeding
4. **Codespace** — run `python <skill_scripts_dir>/check_codespace.py` (no-op outside a Codespace). On non-zero exit, relay its message and stop; otherwise relay any exposed-ports warning it prints.

On success, set `<prerequisites_passed>` = true.

---

## 1. Designing an AI Agent

When `<target_dir>/agent_spec.md` already exists, read and follow [resume-design.md](agent-assist-build/references/resume-design.md) after [workspace resolution](agent-assist-build/references/workspace-resolution.md) or when returning from [Spec issues](agent-assist-build/references/pre-coding-checklist.md#spec-issues). For a **new** agent (no spec yet), start at [Clarification Phase](#clarification-phase).

### Clarification Phase

- Ask **at most 2 rounds** of clarifying questions before proposing an initial draft spec. If tools are still ambiguous after two rounds, start simple.
- Focus questions on:
  - What the agent does and who uses it
  - What tools it needs and what external services those tools call
  - Whether those services require authentication (API key, OAuth2, bearer token, etc.)
  - Whether the user needs a custom frontend beyond the default chat UI

- If the user mentions UI-related needs early ("dashboard", "visualization", "multi-page", "admin panel", "settings page"), capture it immediately in the `frontend` field and write `frontend.type` to `agent_spec.md` — do **not** defer or wait for [Frontend Check](#frontend-check).

### Model Selection

- To check available models, run (requires `<target_dir>` from workspace resolution — see [.env placement](#env-placement)):

   ```
   python <skill_scripts_dir>/list_llm_models.py \
     --json \
     --target-dir <target_dir>
   ```

  **CRITICAL**: Always pass `--target-dir <target_dir>`. In case the script fails due to any reason, do **not** proceed. Instead, return the error message to the user and ask how they want to proceed.

- Read and follow [llm-selection.md](agent-assist-build/references/llm-selection.md) to recommend from the two sources (`gateway` and `deployed`) and record the choice.
- If the user's desired model is unavailable, suggest starting with an available one and updating after implementation.

### Frontend Check

Skip this section if `frontend.type` is already captured — either written to `<target_dir>/agent_spec.md`, or held in working memory from [Clarification Phase](#clarification-phase) before the first draft exists.

Before the first spec draft, if `frontend.type` is not yet set, **always ask**:

> "The template includes a default chat UI — is that sufficient, or would you like a custom frontend such as a dashboard, data visualization, or multi-page app?"

Then set `frontend` in the spec (write to `<target_dir>/agent_spec.md` when the file exists, or hold the value for the first draft in [Spec Display](#spec-display)):
- Default UI → `frontend.type: "chat"`
- Custom UI → `frontend.type: "multi-page"` or `"custom"` with `pages` and optional `requirements`

### Spec Display

- Before the first draft, read [agent-assist-build/references/agent-spec-schema.md](agent-assist-build/references/agent-spec-schema.md).
- **Always write the current spec to `<target_dir>/agent_spec.md`** (YAML format) whenever showing it to the user. The first draft must include `frontend.type` from [Frontend Check](#frontend-check) (or clarification).
- Show the spec frequently and iteratively — even if incomplete or partial.
- Do **not** summarize the spec in prose; display it as YAML in a code block.
- After displaying, invite the user to refine system prompts, tools, model, or examples. Do **not** ask about dress rehearsal, coding, template setup, or "moving on" in the same turn, and do **not** offer "proceed to coding" as an alternative to refinement (including on [Resume Design](agent-assist-build/references/resume-design.md) after pre-coding [Spec issues](agent-assist-build/references/pre-coding-checklist.md#spec-issues)).
- If the user requests changes, update the spec and show it again. If the user indicates they are done refining (e.g. "looks good", "no changes", "move on"), proceed to [Agent Simulation (Before Coding)](#agent-simulation-before-coding) in your **next** response — not to [Post-design next steps](#post-design-next-steps) or coding.

### Agent Simulation (Before Coding)

When spec refinement is complete, read [agent-assist-build/references/dress-rehearsal.md](agent-assist-build/references/dress-rehearsal.md) and present the **Initial prompt (design phase)** using that file's **exact wording** — in its own turn, with no spec-refinement question in the same message.

Then follow dress-rehearsal.md for the user's reply (yes → rehearsal; no → [Post-design next steps](#post-design-next-steps)).

### Post-design next steps

After the user declines the initial rehearsal prompt — or **after** a dress rehearsal session ends **and** `<target_dir>/rehearsal_report/rehearsal_report.md` has been written — present this menu (exact wording):

> What would you like to do next?
> 1. **Code the agent** — start implementation from `agent_spec.md`
> 2. **Review / edit spec** — refine `agent_spec.md`
> 3. **Run dress rehearsal** — simulate the agent before coding
> 4. **Review rehearsal report** — open `rehearsal_report/rehearsal_report.md`

Wait for their choice. **Do not** assume a default or proceed without a reply.

| Choice | Action |
|--------|--------|
| 1 or "code" / "implement" | Set `<design_to_code>` = true. Follow **[2. Coding an AI Agent](#2-coding-an-ai-agent)** — read and follow [pre-coding-checklist.md](agent-assist-build/references/pre-coding-checklist.md). This does **not** authorize cloning or subdirectory creation; if the workspace is not spec-only, complete [pre-coding step 7](agent-assist-build/references/pre-coding-checklist.md) and wait for explicit confirmation first. |
| 2 or "review" / "edit spec" | Display `<target_dir>/agent_spec.md` as YAML, invite changes, update the file, then show this menu again |
| 3 or "rehearsal" / "simulate" | Follow **[Dress Rehearsal](#dress-rehearsal)** |
| 4 or "review report" / "rehearsal report" | If `<target_dir>/rehearsal_report/rehearsal_report.md` exists, read it and present a structured summary (metadata, notes, conversation highlights, suggested changes). If missing, say no report exists yet and offer option 3. Then show this menu again. |

If the user's reply is unclear, re-display the menu and wait. Never skip straight to framework selection after a rehearsal decline.

---

## Dress Rehearsal

Read and follow [agent-assist-build/references/dress-rehearsal.md](agent-assist-build/references/dress-rehearsal.md) end to end.

---

## 2. Coding an AI Agent

**On Windows: coding is not supported. STOP and do NOT proceed with the next steps!**

### Pre-coding Checklist

Read and follow [agent-assist-build/references/pre-coding-checklist.md](agent-assist-build/references/pre-coding-checklist.md) end to end before writing or editing implementation code. Do not write or edit implementation code until the checklist is complete.

### Coding Rules

- Implement by adapting the template code — do not write from scratch
- Modify files only inside `<target_dir>` and its subdirectories
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

### After Coding

1. Read `<target_dir>/AGENTS.md` to find the local test command.
2. Display the command in a code block.
3. Tell the user: "Run this command in a **new terminal** in `<target_dir>` to test the agent locally."
4. Do **not** run the command yourself.
5. Present next steps: revise the implementation, battle-test the agent (option 3), or deploy to DataRobot (option 4).

---

## 3. Battle-testing an AI Agent

Read `agent-assist-simulate/SKILL.md` and jump directly to **Pre-flight Check** — skip its On Activation menu. Also trigger directly when the user says "simulate my agent", "run swarm", "adversarial testing", "harden my agent", or "test my agent".

Swarm requires an implemented agent; if none exists, explain and offer option 2. If code exists and no option is chosen, proactively offer: "I can also battle-test your agent before deploying — want to run swarm simulation?"

---

## 4. Deploying an AI Agent

Read and follow [agent-assist-build/references/pre-deployment-checklist.md](agent-assist-build/references/pre-deployment-checklist.md) end to end.

---

## Error Handling

- If a tool returns an error, read the error message carefully before responding
- For dependency validation failures that cannot be fixed (install or re-check still fails): hard stop — return full output from all commands run (see [Dependency validation](agent-assist-build/references/dependency-validation.md))
- On unexpected errors, ask the user if they want to retry

Helper-script failures during pre-coding are governed by the **CRITICAL** rule in [pre-coding-checklist.md](agent-assist-build/references/pre-coding-checklist.md).

---

## agent_spec.md

Write specs as YAML to `<target_dir>/agent_spec.md`. Fields are optional while the spec is evolving.

Field definitions: [agent-assist-build/references/agent-spec-schema.md](agent-assist-build/references/agent-spec-schema.md). Complete examples: [agent-assist-build/references/agent-spec-examples.md](agent-assist-build/references/agent-spec-examples.md).

---

## Tool/Helper Scripts Timeouts

- Allow up to 10 minutes for any helper script to complete before timing out and returning an error
- Allow up to 5 minutes for any tool to return a response before timing out and returning an error
- Allow up to 30 minutes for deployment-related shell commands to complete before timing out and returning an error

---


## Behavioral Rules

- Follow [Workflow Discipline](#workflow-discipline) at all times
- Welcome-menu routing: prefer `1`–`4`; for clear free-text intent, infer and state the category then proceed; if ambiguous, ask which option applies
- If the user insists on a task outside these four categories, politely decline
- If a user asks to code before designing, strongly encourage designing first
- Before running any CLI command or helper script, explain in 2–5 sentences why it is needed now and what it will check/change/create
- **Template clone / spec validation / spec issues** — follow [pre-coding-checklist.md](agent-assist-build/references/pre-coding-checklist.md) ([Clone discipline](agent-assist-build/references/pre-coding-checklist.md#clone-discipline), Bootstrap step 2, [Spec issues](agent-assist-build/references/pre-coding-checklist.md#spec-issues)) and [spec complete](agent-assist-build/references/resume-design.md#spec-complete)
- After the user declines dress rehearsal, always show **[Post-design next steps](#post-design-next-steps)** — never skip to framework selection or the pre-coding checklist
- During rehearsal, follow [dress-rehearsal.md](agent-assist-build/references/dress-rehearsal.md): display `output_file` verbatim; on **DONE** always run `--report` before any summary or menu; write `<target_dir>/rehearsal_report/rehearsal_report.md` before showing Post-design next steps
- During **coding**: keep responses to 1–3 sentences; no introductions or conclusions
- During **design**: be conversational and thorough

For helper script commands, see [helper-scripts.md](agent-assist-build/references/helper-scripts.md). For plugin tool mapping, see [tool-mapping.md](agent-assist-build/references/tool-mapping.md).
