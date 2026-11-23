---
name: datarobot-agent-harden
description: >-
  Use when the user asks to harden an agent, asks whether an agent is production ready, or
  wants one pre-deployment readiness verdict that combines adversarial swarm simulation with
  an enterprise-readiness gap analysis. Also offer it after Agent Assist finishes coding.
---

# DataRobot Agent Harden

Runs two existing skills on one implemented agent, then gives one verdict:

1. **Swarm simulation**: `datarobot-agent-assist`'s `agent-assist-simulate` sub-skill, which
   checks how the agent behaves under attack, ambiguity and pressure.
2. **Gap analysis**: `datarobot-gap-analysis`, which checks the code against security,
   governance, reliability and regulatory standards.

This skill does not rewrite either check. Each parent skill writes its own report, and
this skill combines them into one report, `harden-report.md`, that links to both.

Read both parent `SKILL.md` files before starting. When this skill says "follow simulate
Step N" or "follow gap-analysis section N", run that step as written, except where this file
says otherwise.

---

## Setup

- `<harden_scripts>` is the `scripts/` directory next to this file.
- `<python>` is `.venv/bin/python3` if it exists, otherwise `python3` (3.11+).
- Run commands from the agent project root (`<target_dir>`).

```bash
<python> <harden_scripts>/harden.py preflight
```

This prints JSON. `parent_skill_scripts.simulate` is `<sim_scripts>` and
`parent_skill_scripts.gap_analysis` is `<gap_scripts>`.

- If `ok` is false, report `problems` and stop. A missing spec or missing code means
  routing the user to `datarobot-agent-assist` (design or code).
- If `git.is_repo` is false or `git.clean` is false, say fixes need a clean git
  worktree. Ask the user to commit or stash the `git.dirty` files, then rerun preflight.
  Do not stash for them.
- Preflight adds the files the parent skills generate to `.git/info/exclude`. That file is
  local and never committed, so the reports don't block the clean-tree check later.
- Run the prerequisite checks from both parent skills once (Python, uv, `dr`, `dr auth
  check`). If credentials fail, invoke `datarobot-setup`.

Tell the user the plan in one short message: swarm first, then gap analysis, then one list
of proposed fixes, then the verdict.

---

## Step 1: Swarm simulation

Follow simulate **Pre-flight Check**, **Step 1**, **Step 2** and **Step 3**. Use `<sim_scripts>`
as its `<skill_scripts_dir>`. Change only these points:

- **After `native_scenarios.py finalize`**, add saved regression cases from earlier runs:

  ```bash
  <python> <harden_scripts>/harden.py suite-load
  ```

  If `added` is not empty, list those names under "Regression (saved breaches)" in the
  candidate review. They are confirmed together with the new scenarios.

- **Step 4**: run only `native_convergence.py initialize`, then create
  `.datarobot/swarm/changes.json` as simulate Step 4 says. Do **not** start the fix loop.
  Fixes are proposed in Step 3 below, together with the gap-analysis fixes.

Keep the opencode server running. Step 4 below reuses it.

---

## Step 2: Gap analysis

Follow gap-analysis **section 2** on the local project path. Use `<gap_scripts>` as its
`<skill_scripts_dir>` and `--out gap-report.md`. Relay the report links it prints. Summarize
it as in gap-analysis **section 3**. Skip gap-analysis section 4. Fixes are handled in Step 3.

---

## Step 3: One fix list

```bash
<python> <harden_scripts>/harden.py match --gap-findings gap-findings.json
```

Read `.datarobot/harden/fix-candidates.json`. Each swarm breach lists the gap findings that
may share its root cause (`possibly_same_root_cause_as`). These pairings are guesses based
on shared tool and function names. For each one, read the breach transcript and the
finding's code location, then decide.

- **Same root cause**: show one fix and name both sources.
- **Different**: keep them as separate items.

Record each decision so the report merges or cross-references the pair. `<n>` is the
finding's `finding_index` in `fix-candidates.json`:

```bash
<python> <harden_scripts>/harden.py decide --scenario <scenario_id> --finding <n> --same|--different
```

Show one numbered list with the most severe items first. For each item, give its source
(swarm, gap, or both), severity, what is wrong in one sentence, and the proposed fix:

- **Swarm breach**: a system-prompt addition, or a code guard when the problem is
  structural (as in simulate Step 4, sub-step 1).
- **Gap `auto`**: the deterministic codemod.
- **Gap `assisted`/`advisory`**: the finding's agent prompt. You carry it out.
- **Gap structural or Re-platform**: not fixed here. Point to gap-analysis section 5.

Then ask **once**: "Apply all, apply some (give numbers), or apply none?"

Close every swarm breach the user did not approve, so it isn't rerun:

```bash
<python> <sim_scripts>/native_convergence.py skip agent_spec.yaml --scenario <scenario_id> [--scenario <scenario_id> ...]
```

Skip this if all swarm breaches were approved.

---

## Step 4: Apply and retest

Only for approved items. Fixes land on **one** branch. Nothing is pushed and no PR is opened.
If simulate Q6 marked tools as `is_readonly` in `agent_spec.yaml`, the worktree is no longer
clean. Ask the user to commit that change first.

1. **Branch.**
   - If any gap `auto` fixes are approved, run them first. They create the branch:

     ```bash
     uv run <gap_scripts>/run_gap_analysis.py . --fix --select <ids> --from gap-findings.json
     ```

   - Otherwise, create the branch yourself:
     `git checkout -b harden-fixes/<UTC timestamp>`.

   Record the branch as `<fix_branch>`.
2. **Swarm fixes**: apply each approved prompt patch or code guard as simulate Step 4 sub-step
   1 says. Keep `agent_spec.yaml` and the implementation's `SYSTEM_PROMPT` in sync.
3. **Assisted gap fixes**: carry out each approved agent prompt on the same branch.
4. **Retest swarm**: run simulate Step 4 sub-steps 2–3 (rerun each scenario you fixed, then
   `advance`) until the status is `complete`. Don't propose new fixes inside this loop. If
   a scenario still breaches, it ends as exhausted and goes into the verdict.
5. **Re-score gaps**: if gap fixes were applied, rerun the gap analysis on the branch with
   `--out gap-report-after.md`.
6. **Show the diff**: `git diff --stat` plus a short summary of every change. Ask whether the
   user wants to commit. Never push.

If nothing was approved, skip this step. The verdict then reflects the agent as it is.

---

## Step 5: Verdict

Save the first-pass swarm breaches as permanent test cases. This must run before the swarm
directory is cleaned up:

```bash
<python> <harden_scripts>/harden.py suite-save
```

This writes `user_datasets/swarm-breaches-<timestamp>.json` and lists it in
`user_datasets/suite.json`. Later runs load it with `suite-load`. Treat these files as
project files the user should commit, on the fix branch if there is one.

Follow simulate **Step 5**, but save the `report` output:

```bash
<python> <sim_scripts>/native_convergence.py report agent_spec.yaml \
  --output eval_report.md \
  --json-out eval-results.json \
  --changes .datarobot/swarm/changes.json > .datarobot/harden/eval-summary.json
```

Then stop the opencode server and clean up `.datarobot/swarm/` as simulate Step 5 says.
Then write the merged report:

```bash
<python> <harden_scripts>/harden.py report \
  --eval-summary .datarobot/harden/eval-summary.json \
  --gap-findings gap-findings.json \
  --gap-report gap-report.html --gap-report gap-report.md \
  [--gap-report gap-report-after.md] [--fix-branch <fix_branch>]
```

If `gap-report-after.md` exists, pass the `gap-findings.json` written by that run. If the
gap analysis ran with a custom `--policy` that changes `fail_on`, pass the same severities
with `--gap-fail-on` (for example `--gap-fail-on critical,high,medium`).

This writes `harden-report.md` and prints the verdict as JSON.

Present the verdict:

```
Verdict: READY | READY WITH WARNINGS | NOT READY
Blocking: <each blocking reason, or "none">
Warnings: <each warning, or "none">
Swarm: <passed>/<total> passed, <exhausted> unresolved
Gap analysis: <findings> findings, <open_blocking> open blocking, <fixed> fixed, posture <posture>
Fix branch: <fix_branch or "no changes">

Reports
- Harden report: <reports.harden_report>
- Swarm simulation: <reports.swarm_eval_report>
- Gap analysis: <each reports.gap_analysis_reports link>
- Regression suite: <reports.regression_suite>
```

Use the links exactly as printed. Don't summarize the reports again unless the user asks.

**Next steps**: review a report, rerun hardening after more changes, or deploy with
`datarobot-agent-assist` option 4. Deploy only after the user has committed the fix branch.
