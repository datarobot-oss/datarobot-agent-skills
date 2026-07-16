## Pre-coding Checklist

Run this checklist when the user enters **[2. Coding an AI Agent](../SKILL.md#2-coding-an-ai-agent)** — including when offered from a failed pre-deployment check.

**Same-session design → code:** `<target_dir>` is already set — skip **Bootstrap** steps 1–2 and start at **Template setup**.

---

### Bootstrap

1. **Confirm `<target_dir>`** — the project root for this session (set in [Workspace Resolution](workspace-resolution.md)). All paths and scripts use this directory.

2. **Confirm spec** — read `<target_dir>/agent_spec.md`. It must exist and meet the [Before Coding Begins](../SKILL.md#before-coding-begins) gate. If missing or incomplete, stop and resolve before continuing.

---

### Template setup

3. **Read `REPO_URL`** from `REPO_URL` in `<skill_scripts_dir>/clone_template.py`. This is the only canonical template repository URL — use it for remote comparison and cloning.

4. **Classify `<target_dir>`** (evaluate in order; first match wins):

   | Classification | Conditions |
   |----------------|------------|
   | **Existing template** | Git repository, `origin` matches `REPO_URL`, `AGENTS.md` present |
   | **Spec-only** | Not existing template, and directory contains only `agent_spec.md` and/or `.env` (no other files or directories) |
   | **Everything else** | Any other state — including wrong git remote, git repo without `AGENTS.md`, or extra files/directories (e.g. `src/`, `.datarobot/`, `.gitignore`) |

5. **Existing template** — notify the user the template is already present in `<target_dir>`. Then:

   a. If `.datarobot/answers/agent-agent.yml` contains `agent_template_framework` → skip framework selection (step 8).

   b. If `.env` exists (setup was run previously) → skip `setup_template.py` (step 9).

   c. Continue to step 10 (dependency check).

6. **Spec-only** — clone and set up the template in `<target_dir>`:

   a. **Move `agent_spec.md` aside** if present — move to a temp location (e.g. `/tmp/agent_spec.md.bak`) before cloning so it is not overwritten. Restore it after cloning completes.

   b. **Clone the template:**

   ```
   python <skill_scripts_dir>/clone_template.py \
     --target-dir <target_dir>
   ```

   c. Continue to framework selection (step 8).

7. **Everything else** — conflicting workspace. Do not clone into `<target_dir>` as-is.

   a. Explain what was found in `<target_dir>`.

   b. Offer to create the agent in a subdirectory (default name: `new-datarobot-agent`). Tell the user that `agent_spec.md` will be **moved** into that subdirectory (not copied) so there is a single project location. Ask the user to confirm or provide a different subdirectory name.

   c. If the subdirectory already exists: warn that using it will **clear everything** in that subdirectory. Ask for confirmation. If the user declines, ask for a different name or return to the [welcome menu](../SKILL.md#on-activation).

   d. If the user agrees:

      - **Move** (do not copy) `<target_dir>/agent_spec.md` into the subdirectory if it exists in the parent. The parent must not keep a duplicate — a stale cwd spec breaks future sessions.
      - Clear the subdirectory contents if it already exists.
      - Set `<target_dir>` to the subdirectory (automatic update — do not ask the user to reset `<target_dir>`).
      - Run clone (step 6b), framework selection (step 8), setup (step 9), and dependency check (step 10) in the new `<target_dir>`.

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

   Wait for the user's reply. Do not assume or default to any framework. If their next message is not a framework choice (silence, unrelated text), re-display the options and wait again — do not proceed with any other coding step. Once the user replies, map their choice to the corresponding value (`langgraph`, `crewai`, `llamaindex`, `nat`, `base`) and run:

   ```
   python <skill_scripts_dir>/select_framework.py \
     --target-dir <target_dir> \
     --framework <value>
   ```

   Invalidate `<dependency_check_passed>` after this step.

9. **Setup** (skip if step 5b applied):

   ```
   python <skill_scripts_dir>/setup_template.py \
     --llm-model <model-name> \
     --target-dir <target_dir>
   ```

   Use the `model` field from `agent_spec.md` as `--llm-model`; if absent, use the model selected during the design phase.

   Invalidate `<dependency_check_passed>` after this step.

10. **Validate dependencies** — run after setup completes:

    ```
    dr dependency check
    ```

    Run in `<target_dir>`. Follow the [Dependency check session rule](../SKILL.md#dependency-check-session-rule).

    **CRITICAL**: On non-zero exit, return the full output to the user and stop. Do not attempt to resolve automatically.

11. **Re-read `<target_dir>/AGENTS.md`** now that the template is ready.

12. **Recreate the TODO list** based on `agent_spec.md` — break down the implementation into discrete steps and add them to the TodoWrite tool.

**CRITICAL**: If any helper script fails, do **not** proceed with coding. Return the error message to the user and ask how they want to proceed.
