## Pre-deployment Checklist

Run this checklist when the user enters **[3. Deploying an AI Agent](../SKILL.md#3-deploying-an-ai-agent)** — including after coding when the user chooses to deploy.

**Prerequisite:** The agent must be implemented before deployment in the same session. If the user requests deploy without having coded, explain that implementation is required and offer **[2. Coding an AI Agent](../SKILL.md#2-coding-an-ai-agent)** — do not deploy until coding completes. This is the canonical rule; other documents link here.

**Different project:** If the user wants to deploy a different project than the one in this session, tell them to start a new session. Do not switch `<target_dir>` unless the user explicitly asks to change the project directory.

---

### Steps

1. **Resolve `<target_dir>`:**

   - If already set this session (from design or coding) → reuse it. Briefly confirm: *"Deploying from `<target_dir>`."*
   - If unset (typically a deploy-only session) → ask:

     > Which project directory contains your implemented agent (the directory with `AGENTS.md`)?

     Set `<target_dir>` to the user's answer. Do not scan subdirectories automatically.

2. **Read `REPO_URL`** from `REPO_URL` in `<skill_scripts_dir>/clone_template.py`.

3. **Verify implementation** in `<target_dir>`:

   | Check | On failure |
   |-------|------------|
   | `AGENTS.md` exists | Agent is not implemented. Offer **[2. Coding an AI Agent](../SKILL.md#2-coding-an-ai-agent)** on this `<target_dir>` and run the [Pre-coding Checklist](pre-coding-checklist.md) (deploy → coding handoff — skip Bootstrap step 1; run step 2 spec validation, then Template setup). |
   | Git repository with `origin` matching `REPO_URL` | Template is not initialized. Offer coding on this `<target_dir>` (deploy → coding handoff — same as above). |
   | User declines coding | Show the [welcome menu](../SKILL.md#on-activation). Stop. |

   Do **not** check for `agent_spec.yaml` — it is not required for deployment.

4. **Validate dependencies** — read and follow [dependency-validation.md](dependency-validation.md) end to end.

5. **Deploy** — read `<target_dir>/AGENTS.md` and follow deployment instructions **strictly**. Do not deviate without user confirmation.
