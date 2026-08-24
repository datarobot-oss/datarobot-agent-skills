## Pre-coding Checklist

Run this checklist when the user enters **[2. Coding an AI Agent](../SKILL.md#2-coding-an-ai-agent)** — including when offered from a failed pre-deployment check.

**On Windows: coding is not supported — stop and do not proceed** (see [SKILL.md §2](../SKILL.md#2-coding-an-ai-agent)).

**Design → code:** If the user chose **Code the agent** from [Post-design next steps](../SKILL.md#post-design-next-steps), `<design_to_code>` must be true before starting this checklist.

### Entry paths (Bootstrap skip rules)

| Entry | Skip Bootstrap | Start at |
|-------|----------------|----------|
| **Same-session design → code** (`<design_to_code>` is true) | Steps 1–2 | Template setup step 3 |
| **Code after workspace resolution** (`<workspace_resolved>` is true and `<target_dir>` equals `<workspace_resolved_target_dir>`) | Step 1 only | Step 2 (cold Code — field validation and missing-spec recovery) |
| **Deploy → coding handoff** (`<target_dir>` set, template not verified) | Step 1 only | Step 2 (spec validation and missing-spec recovery), then Template setup step 3 |

---

### Bootstrap

1. **Confirm `<target_dir>`** — the project root for this session (set in [Workspace Resolution](workspace-resolution.md)). All paths and scripts use this directory.

   **Skip** when `<workspace_resolved>` is true and `<target_dir>` equals `<workspace_resolved_target_dir>`, or when `<design_to_code>` is true, or on deploy → coding handoff.

2. **Confirm spec** — read `<target_dir>/agent_spec.md`.

   **Skip entirely** when `<design_to_code>` is true (design already produced the spec).

   **Required** on deploy → coding handoff — pre-deployment does not check for `agent_spec.md`, but coding needs a [spec complete](resume-design.md#spec-complete) file before template setup (including `model` for step 9).

   **If the file does not exist**, do not assume Design is required — `<target_dir>` may be wrong.

   - If `<workspace_resolved>` is true and `<target_dir>` equals `<workspace_resolved_target_dir>` (workspace just set this path), ask (exact wording):

     > No `agent_spec.md` found at `<target_dir>` (the path you chose earlier). What would you like to do?
     > 1. **Run Design phase** — create a new spec
     > 2. **Try a different directory**

     Do **not** repeat the workspace-resolution directory question verbatim.

   - Otherwise (no recent workspace resolution for this path), ask (exact wording):

     > No `agent_spec.md` found in `<target_dir>`. What would you like to do?
     > 1. **Run Design phase** — create a new spec
     > 2. **Spec is elsewhere** — point to the directory that contains `agent_spec.md`

   Wait for the user's choice.

   - **Choice 1** (or "design" / "create") → follow **[1. Designing an AI Agent](../SKILL.md#1-designing-an-ai-agent)**. Stop the coding checklist.
   - **Choice 2** (or "elsewhere" / "subdirectory" / "different directory" / "try a different directory") → follow [Path resolution](workspace-resolution.md#path-resolution), then re-run **step 2** on the new `<target_dir>` (field validation only — do not re-run step 1).

   **If the file exists** (cold Code entry only), **validate** the spec before anything in [Template setup](#template-setup). Use [resume-design.md § Spec complete](resume-design.md#spec-complete) — this is a field check only; do **not** enter [Resume Design](resume-design.md) unless the user chooses to edit via [Spec issues](#spec-issues) below.

   **Validation procedure (required — do not skip):**

   1. After reading `<target_dir>/agent_spec.md`, check each required field in order: `system_prompt`, `model`, `frontend.type`, `tools` (key present). If `model` is the `datarobot-deployed-llm` placeholder, `llm_deployment_id` is required too.
   2. **Tell the user the result** in your next message — pass or fail, and list any missing fields (e.g. *"Spec validation failed: missing `model`."* or *"Spec validation passed — all required fields are present."*).
   3. **If all fields pass** → continue to [Template setup](#template-setup) step 3.
   4. **If any field fails** → follow **[Spec issues](#spec-issues)** below. **Stop** — do not classify the workspace, run `ls`, clone, or start template setup until the spec is valid or the user has resolved the issue.

   If the spec is not complete, follow **[Spec issues](#spec-issues)** below. Do not start template setup or coding until the spec is valid.

### Spec issues

When step 2 finds a problem in `agent_spec.md`:

1. Explain the issue briefly (what is missing or invalid).

2. **If the only gap is `tools`** (all other required fields are present), ask (exact wording):

   > The `agent_spec.md` is missing a `tools` definition. Would you like to:
   > 1. **Edit the spec in the Design phase**
   > 2. **Confirm no tools needed** — proceed to coding without tools

   - **Choice 1** (or edit / add tools / fix spec) → set `<design_to_code>` = false. Read and follow [resume-design.md](resume-design.md) through Agent Simulation and Post-design next steps — do not return to coding until the user chooses **Code the agent**. Stop the coding checklist.
   - **Choice 2** (or "no tools" / "none needed") → write `tools: []` to `<target_dir>/agent_spec.md`, then treat `tools` as satisfied. Continue to Template setup step 3.

   **Otherwise** (any other missing or invalid field), ask (exact wording):

   > `agent_spec.md` needs changes before coding can continue. Would you like to edit the spec in the Design phase?

   - **If yes** (or the user asks to add, fix, or update the spec) → set `<design_to_code>` = false. Read and follow [resume-design.md](resume-design.md) through Agent Simulation and Post-design next steps — do not return to coding until the user chooses **Code the agent**. Stop the coding checklist.
   - **If no** → do not proceed to template setup. Re-ask or return to the [welcome menu](../SKILL.md#on-activation).

---

### Template setup

**Prerequisite:** All [spec complete](resume-design.md#spec-complete) fields are present in `<target_dir>/agent_spec.md` — validated in Bootstrap step 2 (cold Code and deploy → coding handoff), or satisfied by same-session design (`<design_to_code>` is true; step 2 skipped). If step 2 reported missing fields, do **not** enter this section — handle [Spec issues](#spec-issues) first.

3. **Read `REPO_URL`** from `REPO_URL` in `<skill_scripts_dir>/clone_template.py`. This is the only canonical template repository URL — use it for remote comparison and cloning. See [helper-scripts.md](helper-scripts.md) for script details.

### Clone discipline

- **No separate clone approval** when classification is **Spec-only** (step 6) — the user already chose to code. Give a brief notice (1–2 sentences), then clone without waiting.
- **Subdirectory confirmation required** when classification is **Everything else** (step 7). Choosing **Code the agent** from [Post-design next steps](../SKILL.md#post-design-next-steps), saying "implement", or `<design_to_code>` being true does **not** satisfy this gate — wait for an explicit reply to step 7b (or 7c if the subdirectory already exists).
- **Destructive actions** (clearing an existing subdirectory) always require explicit confirmation in step 7c before proceeding.
- **Before every clone**, state what will happen: target directory, that the DataRobot agent template will be cloned there, and (for step 7) that `agent_spec.md` will be moved. This notice does not require a reply in step 6; in step 7, the reply must come **before** the notice and clone.

4. **Classify `<target_dir>`** (evaluate in order; first match wins):

   | Classification | Conditions |
   |----------------|------------|
   | **Existing template** | Git repository, `origin` matches `REPO_URL`, `AGENTS.md` present |
   | **Spec-only** | Not existing template, and directory contains only `agent_spec.md` and/or `.env` (no other files or directories) |
   | **Everything else** | Any other state — including wrong git remote, git repo without `AGENTS.md`, or extra files/directories (e.g. `src/`, `.datarobot/`, `.gitignore`) |

   **Deploy → coding handoff:** After classifying, jump to the matching step below — do not re-run Bootstrap step 1.

5. **Existing template** — notify the user the template is already present in `<target_dir>`. Then:

   a. If `.datarobot/answers/agent-agent.yml` contains `agent_template_framework` → skip framework selection (step 8).

   b. If `.env` exists (setup was run previously) → skip `setup_template.py` (step 9).

   c. Continue to step 10 (dependency check).

6. **Spec-only** — clone and set up the template in `<target_dir>`:

   a. **Move `agent_spec.md` aside** if present — move to a temp location (e.g. `/tmp/agent_spec.md.bak`) before cloning so it is not overwritten. Restore it after cloning completes.

   b. **Notify, then clone** — tell the user (1–2 sentences, no wait): *"Your workspace is spec-only. I'll clone the DataRobot agent template into `<target_dir>` now."* Then run [clone_template.py](helper-scripts.md#clone_templatepy).

   c. Continue to framework selection (step 8).

7. **Everything else** — conflicting workspace. Do not clone into `<target_dir>` as-is.

   **STOP. Do NOT create subdirectories, move files, or run `clone_template.py` until the user has replied to step 7b or 7c.**

   a. Explain what was found in `<target_dir>`.

   b. If `<design_messy_cwd>` is true, say: *"During design you were warned this directory has other files."* Then offer the default subdirectory `new-datarobot-agent` (or another name the user provides). Tell the user that `agent_spec.md` will be **moved** into that subdirectory (not copied). Ask the user to confirm or provide a different subdirectory name.

   Otherwise, offer to create the agent in a subdirectory (default name: `new-datarobot-agent`). Tell the user that `agent_spec.md` will be **moved** into that subdirectory (not copied) so there is a single project location. Ask the user to confirm or provide a different subdirectory name.

   Wait for the user's reply. Do **not** treat **Code the agent**, "implement", or `<design_to_code>` as confirmation here.

   c. If the subdirectory already exists: warn that using it will **clear everything** in that subdirectory. Ask for confirmation. If the user declines, ask for a different name or return to the [welcome menu](../SKILL.md#on-activation).

   d. If the user agrees:

      - **Move** (do not copy) `<target_dir>/agent_spec.md` into the subdirectory if it exists in the parent. The parent must not keep a duplicate — a stale cwd spec breaks future sessions.
      - Clear the subdirectory contents if it already exists.
      - Set `<target_dir>` to the subdirectory (automatic update — do not ask the user to reset `<target_dir>`).
      - Tell the user (1–2 sentences): *"I'll clone the DataRobot agent template into `<target_dir>` now."* Then run clone (step 6b), framework selection (step 8), setup (step 9), and dependency check (step 10) in the new `<target_dir>`.

   e. If the user declines: show the [welcome menu](../SKILL.md#on-activation). Do not modify `<target_dir>`.

8. **Framework selection** (skip if step 5a applied):

   **STOP. Do NOT proceed until the user has replied with their framework choice.**

   Ask the user (exact message):

   > Which agentic framework would you like to use?
   > 1. LangGraph
   > 2. CrewAI
   > 3. LlamaIndex
   > 4. NeMo Agent Toolkit (NAT)
   > 5. Base

   Wait for the user's reply. Do not assume or default to any framework. If their next message is not a framework choice (silence, unrelated text), re-display the options and wait again — do not proceed with any other coding step. Once the user replies, map their choice to the corresponding `--framework` value (see [select_framework.py](helper-scripts.md#select_frameworkpy)) and run that script.

   Invalidate `<dependency_check_passed>` after this step.

9. **Setup** (skip if step 5b applied) — run [setup_template.py](helper-scripts.md#setup_templatepy). Use the `model` field from `agent_spec.md` as `--llm-model` (must be present — validated in Bootstrap step 2 for cold Code and deploy handoff, or produced by same-session design). If the spec also carries `llm_deployment_id`, pass it as `--llm-deployment-id`; it selects a DataRobot-deployed LLM, and the script refuses the deployed-LLM placeholder model without it.

   Invalidate `<dependency_check_passed>` after this step.

10. **Validate dependencies** — run after setup completes. Read and follow [dependency-validation.md](dependency-validation.md) end to end.

11. **Re-read `<target_dir>/AGENTS.md`** now that the template is ready.

12. **Recreate the TODO list** based on `agent_spec.md` — break down the implementation into discrete steps and add them to the TodoWrite tool.

**CRITICAL**: If any helper script fails, do **not** proceed with coding. Return the error message to the user and ask how they want to proceed.
