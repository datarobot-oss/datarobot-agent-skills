---
name: datarobot-openspec-af
description: >-
  EXPERIMENTAL — invoke-only during initial testing. Use when the user explicitly
  invokes /datarobot-openspec-af to design and scaffold a DataRobot custom
  application via the OpenSpec artifact chain (proposal → spec → design → AF
  composition → tasks). Do not auto-activate from natural-language triggers.
---

# OpenSpec + AF

A spec-driven skill for designing and building DataRobot custom applications using OpenSpec for the design artifact chain and AF v2 components for project scaffolding.

Intended as a replacement path for `datarobot-agent-assist` once proven.

The AF composition logic (component discovery, question collection, `compose_template.py` invocation) is embedded inline rather than delegated to the `af-component` skill. This keeps the two skills independent.

---

## OpenSpec Assumption

This skill **assumes OpenSpec is already initialized** in the project (`openspec/` directory exists, `openspec/config.yaml` is present). It does not run `openspec init`.

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
   - If missing, **ALWAYS RUN** the install command before proceeding.
   - **ALWAYS RUN** the upgrade command before proceeding.
   - If not authenticated, **ALWAYS RUN** the auth command before proceeding.
4. **OpenSpec** — check that `openspec/config.yaml` exists in the working directory. If it does not exist, tell the user to run `openspec init` first and stop.

---

## Artifact Chain

```
proposal.md → spec.md → design.md ─┐
                                    ├── [AF composition — scaffold project]
                                    └── tasks.md → /opsx:apply
                                         (against real generated code)
```

The composition step is triggered when `design.md` is confirmed and before `tasks.md` is created.

---

## Design Phase

Work through the standard OpenSpec artifact chain:

1. If `proposal.md` does not exist, help the user write one from their description of the application.
2. If `spec.md` does not exist, derive it from `proposal.md` using `openspec generate spec` or write it collaboratively.
3. Create or extend `design.md` to include both standard OpenSpec content (technical decisions, risks, migration plan) and an **Infrastructure** section (see below).

### Infrastructure Section (add to design.md)

```markdown
## Infrastructure

### Selected AF Components
| Module | Reason |
|--------|--------|
| base | Required for all AF v2 projects |
| llm | LLM deployment |
| datarobot_mcp | MCP server exposure |
| agent | Agent application scaffold |

### Collected Answers
| Question | Value | Source |
|----------|-------|--------|
| agent_template_framework | langgraph | user |
| agent_app_name | my-agent | derived (working dir) |
```

To populate this section:

1. Run `dr component list-available --format json`. Use `agent_guidance.summary` for each module to identify which components the application needs.
2. Run `dr component describe <module> --format json` for each selected module.
3. Collect all questions; deduplicate by name across modules.
4. Fill in the Infrastructure section with the selected modules and the answers you plan to provide (marking each as `user` or `derived`).
5. Confirm the Infrastructure section with the user before proceeding.

### Model Selection

Run the helper script to enumerate available models:

```bash
python <skill_scripts_dir>/list_llm_models.py --json
```

**CRITICAL**: If this script fails for any reason, do **not** proceed. Return the error to the user and ask how they want to proceed.

Recommend a `gpt-5`, `claude-4-5`, or `gemini-2.5` model from the list unless the user specifies constraints. Record the chosen model in `spec.md` under a `model:` field.

---

## Optional: Dress Rehearsal (Before Composition)

After `design.md` is confirmed but before running composition, ask the user (exact wording):

> "Would you like to run a dress rehearsal simulation before scaffolding? (recommended)"

Wait for their reply. If they say yes, follow **[Dress Rehearsal](#dress-rehearsal)** end to end. If they decline, proceed directly to composition.

---

## AF Composition Step (Between design.md and tasks.md)

Runs inline after `design.md` is confirmed (and after any dress rehearsal):

1. Extract the module list from the Infrastructure section of `design.md`. Confirm with user if ambiguous.
2. Re-run `dr component describe <module> --format json` for each selected module to collect all questions.
3. Deduplicate questions by name across modules. Partition into `ask_user: true` / `ask_user: false`.
4. For `ask_user: true` questions: ask the user one at a time, showing `help` and `reason`.
5. **STOP. Do NOT run `compose_template.py` until all `ask_user: true` questions have been answered.**
6. For `ask_user: false` questions: derive silently using the derivation map below.
7. Run `compose_template.py`:

```bash
python <skill_scripts_dir>/compose_template.py \
  --modules '<json array>' \
  --answers '<json object of label.question=value>' \
  --target-dir .
```

Pass `--registry-uri file://...` if the registry is not yet live.

**CRITICAL**: On failure, do **not** proceed. Return the full error to the user.

8. Run `dr dependency check`. Any non-zero exit is a hard error — return output to user and stop.
9. Run `setup_template.py` using the `model` from `spec.md`:

```bash
python <skill_scripts_dir>/setup_template.py \
  --llm-model <model-name> \
  --target-dir .
```

**CRITICAL**: On failure, do **not** proceed. Return the error to the user.

10. **STOP.** Tell the user the scaffolded project is ready and ask them to confirm it looks correct before proceeding to `tasks.md`.

#### Derivation map for `ask_user: false` questions

| Question name | Derivation |
|---|---|
| `agent_app_name`, `llm_app_name` | Slugify working directory name |
| `mcp_app_name` | `mcp_server` |
| `copyright_year` | Current year |
| `mcp_development_port` | `8080` |
| All others | Declared default |

---

## Coding Phase (tasks.md → /opsx:apply)

After the user confirms the scaffolded project:

1. Create `tasks.md` from `spec.md` in the context of the scaffolded project — each task should reference specific files to modify in the generated template.
2. Tell the user to invoke `/opsx:apply` to implement the tasks (adapting the template code rather than writing from scratch).
3. Read `AGENTS.md` in the scaffolded project for local test and deployment instructions. Display the local test command in a code block.

---

## Dress Rehearsal

Simulate the agent interactively before writing any code. Responses go through the DataRobot LLM Gateway; the rehearsal script handles API calls, state, and output.

**Engine location:** `<skill_scripts_dir>/rehearsal.py`

### Step 1 — Initialize the session

```bash
python <skill_scripts_dir>/rehearsal.py --init [--spec agent_spec.md]
```

If `agent_spec.md` does not exist and no path was provided, say so and stop. (For `openspec-af`, derive a temporary `agent_spec.md` from `spec.md` before running rehearsal.)

The script creates a unique session directory in the system temp dir and prints two lines:
```
session=<session_dir>
output=<output_file>
```

Retain `session_dir` for all subsequent calls. Read the `output_file` and display its contents verbatim, then say:

> You are now the **end user** of this agent. Type messages as a real user would.
>
> **Out-of-character commands:**
> - `NOTE: <text>` — record a design observation
> - `DONE` — end the session and generate your feedback report

### Step 2 — Simulation loop

Keep track of any notes and the number of turns as the session progresses.

**On each user message:**

- If it starts with `NOTE:` — acknowledge the note, prompt for next message. Do not call the script.
- If it is `DONE` — proceed to Step 3.
- Otherwise — run the turn:

```bash
python <skill_scripts_dir>/rehearsal.py --session {session_dir} "{user_message}"
```

The script prints `output=<output_file>`. Read that file and display its contents verbatim.

If the script exits non-zero, display the error and ask whether to continue or abort.

### Step 3 — Feedback report

Review the session and surface concrete findings in these areas (only include areas where you have something specific to say):

- **System prompt** — wording, missing constraints, persona, tone
- **Tools** — input/output scoping, missing or redundant tools, argument naming
- **Model** — only flag if clearly wrong for the observed task complexity
- **Example prompts** — additions or revisions based on what was tested
- **Other** — edge cases, UX concerns, data dependency risks

Write the report:

```
════════════════════════════════════════════
  DRESS REHEARSAL REPORT
════════════════════════════════════════════

{1–2 sentences: what was tested and how the agent performed overall}
{If notes were recorded: "Notes: " followed by each note on its own line, prefixed with —}

Suggested changes:
1. {specific, actionable change}
…
{If nothing worth changing: "No changes recommended."}

════════════════════════════════════════════
```

Record observations as notes in `design.md`. Then proceed to composition.

---

## Error Handling

- If a tool returns an error, read the error message carefully before responding.
- For template-prep **warnings**: try to resolve yourself.
- For template-prep **errors**: return the message to the user and ask how to proceed.
- On unexpected errors, ask the user if they want to retry.

---

## Tool Timeouts

- Allow up to 10 minutes for any helper script to complete before timing out.
- Allow up to 5 minutes for any tool to return a response before timing out.
- Allow up to 30 minutes for deployment-related shell commands before timing out.

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
