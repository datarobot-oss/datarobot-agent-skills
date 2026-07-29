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

## Workflow Discipline

Follow this skill **sequentially**. These rules apply to every phase — design, coding, deployment, and every referenced checklist.

1. **Section order** — Complete each section and subsection in the order it appears in this file. Do not jump to a later section until the current one is finished.
2. **Reference files** — When this skill says **read and follow** a file under `references/`, read that file first, then execute every step in that file in order. Do not substitute a summary, shortcut, or a later menu for steps defined in the reference.
3. **Explicit skips only** — Skip a step only when this skill or the referenced file explicitly says to skip it (e.g. Pre-requisite Check when `<prerequisites_passed>` is true, or Frontend Check when `frontend.type` is already set).
4. **No auto-advance** — Completing one step (e.g. writing the spec, the user saying "move on", or a command succeeding) does not authorize skipping remaining steps. Proceed only when the current section or reference directs you to the next step.
5. **Menus and prompts** — When a section presents a menu or asks a question, wait for the user's reply. Do not assume a default or proceed on your own.
6. **One design gate per turn** — During design, do not combine prompts from different subsections in one message (e.g. do not ask about spec refinement and dress rehearsal in the same turn).

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

Show this menu first. After the user selects an option (`1`, `2`, or `3`), run the **[Pre-requisite Check](#pre-requisite-check)** (once per session) and then the **[Script Path Resolution](#script-path-resolution)**.

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

- `<target_dir>` — project root for design, coding, and deployment. Set during [Workspace Resolution](references/workspace-resolution.md) or the [Pre-deployment Checklist](references/pre-deployment-checklist.md). Reuse across phases in the same session. Only change when the user explicitly asks, during [pre-coding Bootstrap step 2](references/pre-coding-checklist.md) (spec path recovery), during [pre-coding subdir recovery](references/pre-coding-checklist.md) (step 7), or in a new session.
- `<prerequisites_passed>` — `false` until the [Pre-requisite Check](#pre-requisite-check) completes successfully once this session.
- `<workspace_resolved>` — `false` until [Workspace Resolution](references/workspace-resolution.md) completes for menu options **1** or **2**.
- `<workspace_resolved_target_dir>` — the `<target_dir>` set when workspace resolution last completed.
- `<design_to_code>` — `false` until the user chooses **Code the agent** from [Post-design next steps](#post-design-next-steps) in the same session after design.
- `<design_messy_cwd>` — `false` until design runs in cwd with files other than `agent_spec.md` / `.env` (see [workspace-resolution](references/workspace-resolution.md)).
- `<dependency_check_passed>` — `false` until a passing `dr dependency check` in `<target_dir>`.
- `<dependency_check_target_dir>` — the `<target_dir>` value when the last check passed.

### `.env` placement

Project credentials and config live **only** at `<target_dir>/.env` — never in cwd when `<target_dir>` is a subdirectory.

- Complete [Workspace Resolution](references/workspace-resolution.md) before any step that needs credentials or creates a `.env` file (model selection, dress rehearsal, template setup).
- Always pass `--target-dir <target_dir>` to helper scripts that read or create `.env` (`list_llm_models.py`, `rehearsal.py`, `setup_template.py`).
- Do **not** run `dr dotenv setup` manually in cwd — use helper scripts with `--target-dir <target_dir>` so `.env` is created in the project root.

### Dependency check session rule

Before running dependency validation:

- If `<dependency_check_passed>` is true and `<target_dir>` equals `<dependency_check_target_dir>`, skip validation.
- Otherwise, read and follow [references/dependency-validation.md](references/dependency-validation.md) in `<target_dir>`.

Invalidate `<dependency_check_passed>` (set to false) when:

- `<target_dir>` changes
- `clone_template.py`, `select_framework.py`, or `setup_template.py` runs in `<target_dir>`

### Welcome menu reset

When showing the [welcome menu](#on-activation) again (e.g. user declined pre-coding step 7): set `<workspace_resolved>` = false, clear `<workspace_resolved_target_dir>`, `<design_to_code>` = false, and `<design_messy_cwd>` = false. Keep `<prerequisites_passed>` true.

---

## Workspace Resolution

Read and follow [references/workspace-resolution.md](references/workspace-resolution.md) after menu options **1** or **2**.

---

## Pre-requisite Check

If `<prerequisites_passed>` is true, skip this section.

Otherwise, run in order before proceeding:

1. **Git** — run `git --version`. If missing, tell the user to install from https://git-scm.com and stop.
2. **Python** — run `python --version`. If missing or below 3.11, tell the user to install Python 3.11+ from https://python.org and stop.
3. **DataRobot CLI** — read and follow [references/dr-cli-setup.md](references/dr-cli-setup.md):
   - If missing, **ALWAYS RUN** the install command before proceeding
   - **ALWAYS RUN** the upgrade command before proceeding
   - If not authenticated, **ALWAYS RUN** the auth command before proceeding
4. **Codespace** — run `python <skill_scripts_dir>/check_codespace.py` (no-op outside a Codespace). On non-zero exit, relay its message and stop; otherwise relay any exposed-ports warning it prints.

On success, set `<prerequisites_passed>` = true.

---

## 1. Designing an AI Agent

When `<target_dir>/agent_spec.md` already exists, read and follow [resume-design.md](references/resume-design.md) after [workspace resolution](references/workspace-resolution.md) or when returning from [Spec issues](references/pre-coding-checklist.md#spec-issues). For a **new** agent (no spec yet), start at [Clarification Phase](#clarification-phase).

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

- Each entry carries a `source`: `gateway` (an LLM Gateway catalog model) or `deployed` (an existing DataRobot text-generation deployment). Deployed entries are how an environment with the gateway disabled or empty — typically on-prem — still gets a model.
- Recommend a `gpt-5`, `claude-4-5`, or `gemini-2.5` **gateway** model from the list unless the user specifies cost or other constraints.
- If none of those preferred families appear in the catalog, pick the highest-capability available gateway model by name — prefer ones containing `large`, `pro`, `opus`, or `sonnet` over `mini`, `haiku`, or `flash`.
- If there are no gateway entries at all, recommend a `deployed` entry, identifying it to the user by its `label` (every deployed entry shares the same `name`).
- Only display the full model catalog when the user **explicitly** asks to browse models.
- If the user's desired model is unavailable, suggest starting with an available one and updating after implementation.

Write the choice to `agent_spec.md` as the entry's `name`. For a `deployed` entry, also write its `deployment_id` as `llm_deployment_id` — the `name` is a shared sentinel, so without the id the selection is lost. See [agent-spec-schema.md](references/agent-spec-schema.md).

Note: a dress rehearsal talks to the LLM Gateway directly, so a deployed model cannot be rehearsed. The rehearsal substitutes a gateway model and says so; the spec's model is unaffected.

### Frontend Check

Skip this section if `frontend.type` is already set in `<target_dir>/agent_spec.md` (e.g. captured during [Clarification Phase](#clarification-phase)).

Before the first spec draft, if `frontend.type` is not yet set, **always ask**:

> "The template includes a default chat UI — is that sufficient, or would you like a custom frontend such as a dashboard, data visualization, or multi-page app?"

Then set `frontend` in the spec (write to `<target_dir>/agent_spec.md` when the file exists, or hold the value for the first draft in [Spec Display](#spec-display)):
- Default UI → `frontend.type: "chat"`
- Custom UI → `frontend.type: "multi-page"` or `"custom"` with `pages` and optional `requirements`

### Spec Display

- Before the first draft, read [references/agent-spec-schema.md](references/agent-spec-schema.md).
- **Always write the current spec to `<target_dir>/agent_spec.md`** (YAML format) whenever showing it to the user. The first draft must include `frontend.type` from [Frontend Check](#frontend-check) (or clarification).
- Show the spec frequently and iteratively — even if incomplete or partial.
- Do **not** summarize the spec in prose; display it as YAML in a code block.
- After displaying, invite the user to refine system prompts, add/modify tools, change the model, or update examples. Do **not** ask about dress rehearsal, coding, template setup, or "moving on" in the same turn — and do **not** offer "proceed to coding" as an alternative to refinement (including on [Resume Design](references/resume-design.md) after pre-coding [Spec issues](references/pre-coding-checklist.md#spec-issues)).
- If the user requests changes, update the spec and show it again. If the user indicates they are done refining (e.g. "looks good", "no changes", "move on"), proceed to [Agent Simulation (Before Coding)](#agent-simulation-before-coding) in your **next** response — not to [Post-design next steps](#post-design-next-steps) or coding.

### Agent Simulation (Before Coding)

When spec refinement is complete, read [references/dress-rehearsal.md](references/dress-rehearsal.md) and present the **Initial prompt (design phase)** using the **exact wording** below — in its own turn, with no spec-refinement question in the same message:

> **Dress rehearsal** is a try-before-you-build session: you chat with your agent design as if it were already running. The agent uses your spec's model and system prompt; tool calls return **simulated** (fake but realistic) data — no real APIs, no deployment, no code written yet. It's a safe way to test prompts, tools, and conversation flow before implementation.
>
> Would you like to run a dress rehearsal simulation first? (recommended)

Then follow dress-rehearsal.md for the user's reply (yes → rehearsal; no → [Post-design next steps](#post-design-next-steps)).

### Post-design next steps

After the user declines the initial rehearsal prompt — or after a dress rehearsal session ends — present this menu (exact wording):

> What would you like to do next?
> 1. **Code the agent** — start implementation from `agent_spec.md`
> 2. **Review / edit spec** — refine `agent_spec.md`
> 3. **Run dress rehearsal** — simulate the agent before coding

Wait for their choice. **Do not** assume a default or proceed without a reply.

| Choice | Action |
|--------|--------|
| 1 or "code" / "implement" | Set `<design_to_code>` = true. Follow **[2. Coding an AI Agent](#2-coding-an-ai-agent)** — read and follow [references/pre-coding-checklist.md](references/pre-coding-checklist.md). This choice does **not** authorize cloning or subdirectory creation — if the workspace is not spec-only, complete [pre-coding step 7](references/pre-coding-checklist.md) and wait for explicit confirmation first. |
| 2 or "review" / "edit spec" | Display `<target_dir>/agent_spec.md` as YAML, invite changes, update the file, then show this menu again |
| 3 or "rehearsal" / "simulate" | Follow **[Dress Rehearsal](#dress-rehearsal)** |

If the user's reply is unclear, re-display the menu and wait. Never skip straight to framework selection after a rehearsal decline.

---

## Dress Rehearsal

Read and follow [references/dress-rehearsal.md](references/dress-rehearsal.md) end to end.

---

## 2. Coding an AI Agent

**On Windows: coding is not supported. STOP and do NOT proceed with the next steps!**

### Pre-coding Checklist

Read and follow [references/pre-coding-checklist.md](references/pre-coding-checklist.md) end to end before writing or editing implementation code. Do not write or edit implementation code until the checklist is complete.

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

---

## Error Handling

- If a tool returns an error, read the error message carefully before responding
- For dependency validation failures that cannot be fixed (install or re-check still fails): hard stop — return full output from all commands run (see [Dependency validation](references/dependency-validation.md))
- On unexpected errors, ask the user if they want to retry

Helper-script failures during pre-coding are governed by the **CRITICAL** rule in [pre-coding-checklist.md](references/pre-coding-checklist.md).

---

## agent_spec.md

Write specs as YAML to `<target_dir>/agent_spec.md`. Fields are optional while the spec is evolving.

Field definitions: [references/agent-spec-schema.md](references/agent-spec-schema.md). Complete examples: [references/agent-spec-examples.md](references/agent-spec-examples.md).

---

## Tool/Helper Scripts Timeouts

- Allow up to 10 minutes for any helper script to complete before timing out and returning an error
- Allow up to 5 minutes for any tool to return a response before timing out and returning an error
- Allow up to 30 minutes for deployment-related shell commands to complete before timing out and returning an error

---


## Behavioral Rules

- Follow [Workflow Discipline](#workflow-discipline) at all times
- If it is unclear whether the request falls into one of the three categories, ask a clarifying question
- If the user insists on a task outside these three categories, politely decline
- If a user asks to code before designing, strongly encourage designing first
- Before running any CLI command or helper script, provide a clear explanation in 2-5 sentences. The explanation must include why this specific command is needed now, what it will check/change/create.
- **Template clone** — follow [Clone discipline](references/pre-coding-checklist.md#clone-discipline): spec-only workspaces get a brief notice then clone; messy workspaces require explicit subdirectory confirmation (step 7) before any clone; never treat **Code the agent** as that confirmation.
- **Pre-coding spec validation** — on cold Code entry and deploy → coding handoff, Bootstrap step 2 must check every [spec complete](references/resume-design.md#spec-complete) field and report pass/fail to the user before workspace classification or template setup. Do not run `ls`, clone, or classify `<target_dir>` until validation passes or [Spec issues](references/pre-coding-checklist.md#spec-issues) is resolved.
- **Pre-coding spec issues** — if `agent_spec.md` has gaps during Bootstrap step 2, do not fix inline; route to Design via [resume-design.md](references/resume-design.md). Exception: missing `tools` only may be waived when the user confirms no tools are needed.
- After the user declines dress rehearsal, always show **[Post-design next steps](#post-design-next-steps)** — never skip to framework selection or the pre-coding checklist
- During **rehearsal turns**: display only the `output_file` contents — never add performance commentary or replace the script's bottom decoration / DONE hint (see [dress-rehearsal.md](references/dress-rehearsal.md))
- During **coding**: keep responses to 1–3 sentences; no introductions or conclusions
- During **design**: be conversational and thorough

For helper script commands, see [references/helper-scripts.md](references/helper-scripts.md). For plugin tool mapping, see [references/tool-mapping.md](references/tool-mapping.md).
