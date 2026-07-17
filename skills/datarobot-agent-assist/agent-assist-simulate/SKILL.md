---
name: datarobot-agent-assist-simulate
description: >-
  Use when the user wants to adversarially test, evaluate, or harden an implemented AI agent before
  deployment; mentions swarm simulation, attack testing, persistence testing, evaluation criteria,
  or eval_report.md.
---

# Agent Assist — Simulate

Adversarially test and harden an implemented agent before deployment. Runs three simulation tracks
(attack, behavior, persistence), then iteratively patches the system prompt through a convergence
loop until all scenarios pass or iterations are exhausted.

---

## Script Path Resolution

Resolve once per session: `<skill_scripts_dir>` is the `scripts/` subdirectory next to this
`SKILL.md`. Confirm it exists. Use the resolved absolute path everywhere.

**Python:** prefer `.venv/bin/python3` if a `.venv/` exists; otherwise `python3`. Store as
`<python>`. Require 3.11+:

```bash
<python> -c "import sys; assert sys.version_info >= (3, 11)"
<python> -c "import pydantic, yaml" 2>/dev/null || <python> -m pip install pydantic pyyaml
```

**OpenCode:**

```bash
opencode --version 2>/dev/null || (dr opencode upgrade && export PATH="$PATH:$HOME/.opencode/bin")
```

**Auth:**

```bash
dr auth check
```

If any check fails, surface the error and stop.

---

## Pre-flight Check

1. Confirm `agent_spec.md` exists with a `system_prompt`. If not, route the user to
   `agent-assist-build` and stop.
2. Confirm implementation code exists (`agent.py`, `tools.py`, or `app.py`). If not, route to
   `agent-assist-build` and stop.

---

## Step 1 — Configure

Collect answers in sequence. Do not start simulation until all are answered.

If `agent_config.yaml` already exists, read it and ask:
> "Last time: [persona], [context or none], [iterations] iterations, [eval mode], [model]. Same
> settings or change anything?"

**Q1 — User type:** Read `agent_spec.md` and offer 2–4 domain-specific personas plus
"Other — describe your user segment."

**Q2 — Grounding context (optional):** Ask for customer tickets, support logs, or behavior
descriptions. Save to `user_context.txt` if provided. Skip if the user says "skip."

**Q3 — Iteration limit:** Default 3.

**Q4 — Evaluation mode:** Standard (pass/fail) or scored. Default standard.

**Q5 — Model:** Run `dr opencode models` and present up to ten as a numbered list, with
"Other — enter a model ID" as the last option. Store the choice as `<model>`.

**Q6 — Selective tool execution (optional):** Read the tool definitions in `agent_spec.md` and
identify any that appear to be read-only — no writes, no side effects, names like `get_`, `list_`,
`load_`, `fetch_`, `search_`. If any exist, ask:
> "I can call these tools for real during simulation instead of generating fictional return values:
> [list each with its description]
> Run them for real, or simulate all? Default is simulate."

If the user chooses real execution: edit `agent_spec.md` to add `is_readonly: true` on each
approved tool, then pass `--execution-mode selective_e2e` to `native_scenarios.py configure`.
If the user declines or no read-only tools exist, omit `--execution-mode` (defaults to simulated).

**Start OpenCode server** (once, after model selection):

```bash
dr opencode serve --port 4096 2>/dev/null &
until curl -sf http://127.0.0.1:4096/global/health >/dev/null 2>&1; do sleep 0.25; done
```

Store the PID as `<opencode_server_pid>` and `http://127.0.0.1:4096` as `<opencode_server_url>`.

**Persist config:**

```bash
<python> <skill_scripts_dir>/native_scenarios.py configure agent_spec.md \
  --user-persona "<persona>" \
  --iterations <n> \
  --judge-mode <standard|scored> \
  --model "<model>" \
  [--context user_context.txt]
```

---

## Step 2 — Generate Scenarios

```bash
<python> <skill_scripts_dir>/native_scenarios.py prepare agent_spec.md \
  --config agent_config.yaml
```

Run each generator one at a time. After each, tell the user what was generated:

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-attack \
  --input-path .datarobot/swarm/attack-input.json \
  --response-path .datarobot/swarm/attack-output.json \
  --model <model> --server-url <opencode_server_url>
```
Read `.datarobot/swarm/attack-output.json` and report the scenario count: `"Generated X attack scenarios."`

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-behavior \
  --input-path .datarobot/swarm/behavior-input.json \
  --response-path .datarobot/swarm/behavior-output.json \
  --model <model> --server-url <opencode_server_url>
```
Read `.datarobot/swarm/behavior-output.json` and report: `"Generated X behavior scenarios."`

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-persistence \
  --input-path .datarobot/swarm/persistence-input.json \
  --response-path .datarobot/swarm/persistence-output.json \
  --model <model> --server-url <opencode_server_url>
```
Read `.datarobot/swarm/persistence-output.json` and report: `"Generated X persistence scenarios."`

Validate all outputs:

```bash
<python> <skill_scripts_dir>/native_scenarios.py finalize
```

Read `finalize` stdout and present the candidate list to the user. Ask them to add/remove scenarios or say "run it" to confirm.
Write the authoritative criteria:

```bash
<python> <skill_scripts_dir>/native_scenarios.py confirm --output evaluation_criteria.md
```

---

## Step 3 — Simulate

If `.datarobot/swarm/` exists, ask the user:
> "Previous results exist — run again and archive them? (yes/no)"

If yes, archive the directory with a timestamp (`mv .datarobot/swarm .datarobot/swarm-<timestamp>`)
and continue. If no, stop and let the user review previous results.

Find all implementation files in the working directory (`agent.py`, `tools.py`, `app.py`) and pass
each as a separate `--implementation` flag. Tell the user how many scenarios will run before launching:
> "Running N scenarios across 3 tracks — typically 2–5 minutes."

```bash
<python> <skill_scripts_dir>/native_swarm.py run agent_spec.md \
  --criteria evaluation_criteria.md \
  --config agent_config.yaml \
  --server-url <opencode_server_url> \
  --model <model> \
  --implementation <path> [--implementation <path> ...] \
  [--tools-path <path/to/tools.py>]
```

Include `--tools-path` only when `execution.mode` is `selective_e2e` and `tools.py` exists. Parse
stdout as the summary JSON. Surface any `warning:` lines from stderr before presenting results.

**Present results:**

> "N of M scenarios passed."

List any breaches by track and name.

- If `breached == 0`: skip Step 4 and go to Step 5.
- If `breached > 0`: proceed to Step 4.

---

## Step 4 — Converge

```bash
<python> <skill_scripts_dir>/native_convergence.py initialize agent_spec.md \
  --criteria evaluation_criteria.md \
  --config agent_config.yaml \
  --results .datarobot/swarm/results.json \
  --actual-model "<model>"
```

Parse stdout from `initialize` as JSON — it contains `{"status": "...", "tasks": [...]}`. Each
task has `role`, `task_id`, `input_path`, `response_path`, and (for rerun tasks) `run_dir` — use
these directly when invoking workers. Process each task in the wave, then call `advance`. Parse
`advance` stdout the same way to get the next wave. Repeat until `status` is `complete`. Run one
worker at a time.

**Before each wave**, tell the user what's happening:
- Fixer wave: `"Patching: [scenario] (attempt N of M)"`
- Rerun: `"Retesting: [scenario]"` — report `✓ passed / ✗ breach / ! error` as each finishes
- Diagnoser wave: `"Diagnosing unresolved breach: [scenario]"`

**Fixer / diagnoser tasks:**

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt <generate-fix|diagnose-failure> \
  --input-path <input_path> \
  --response-path <response_path> \
  --model <model> --server-url <opencode_server_url>
```

**Rerun tasks** (runner / fixture / evaluator) — drive each to terminal:

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt <run-scenario|generate-tool-return|evaluate-result> \
  --input-path <input_path> \
  --response-path <response_path> \
  --model <model> --server-url <opencode_server_url>
```

Submit and route from the returned transition:

```bash
<python> <skill_scripts_dir>/native_execution.py submit \
  --run-dir <run_dir> --response <response_path>
```

`submit` prints JSON. If it contains `"role"`, dispatch the next worker using the returned
`input_path` and `response_path`. If it contains a terminal status (`"passed"`, `"breach"`,
`"error"`), record the outcome and move to the next task.

After each wave, advance:

```bash
<python> <skill_scripts_dir>/native_convergence.py advance agent_spec.md
```

When `advance` returns `complete`:
> "Convergence complete. X resolved, Y exhausted."

---

## Step 5 — Report

```bash
<python> <skill_scripts_dir>/native_convergence.py report agent_spec.md \
  --output eval_report.md

kill <opencode_server_pid> 2>/dev/null || true
```

Present passed/total, unresolved, exhausted, patches applied, and readiness. If `ready: false`,
say so explicitly before offering next steps.

For each structural diagnosis, present the scenario, risk, recommendation, and `function_hint`.
Ask:
> "Would you like me to implement these structural fixes?"

Stop and wait. If approved, make only the targeted changes to the hinted function.

**Next steps:**

```
What would you like to do next?
1. Review eval_report.md     — outcomes and unresolved scenarios
2. Re-run simulation         — after further changes
3. Test locally              — run the agent on your machine
4. Deploy                    — deploy the hardened agent to DataRobot
```

- If **1**: read `eval_report.md` and present a structured summary.
- If **2**: return to Step 1 (reuse saved settings or re-collect).
- If **3**: read `AGENTS.md`, display the local test command, tell the user to run it in a new terminal.
- If **4**: follow the deploy instructions in `agent-assist-build/SKILL.md`.

---

## Error Handling

**Step 2 generator failure** — `finalize` prints `role:<role> validation failed: <reason>` for
each invalid output. Retry that generator once with `--rejection-note "<reason>"` and rerun
`finalize`. If it still fails, surface the error and stop.

**Step 4 convergence worker failure** — if `gateway_worker.py` exits non-zero, retry once. After
a second failure, mark the task failed before calling `advance`:

```bash
<python> <skill_scripts_dir>/native_convergence.py fail agent_spec.md \
  --task-id <task_id> --reason "<reason>"
```

**Step 4 rerun worker failure** — if a runner/fixture/evaluator worker exits non-zero, mark the
scenario failed:

```bash
<python> <skill_scripts_dir>/native_execution.py fail \
  --run-dir <run_dir> --reason "<reason>"
```

**Auth errors (401 / UNAUTHORIZED):** Run `dr auth login` and retry immediately.

**Script timeouts:** Allow up to 2 minutes per worker, 10 minutes for `native_swarm.py run`.

---

## Simulation Tracks

| Track | Degrades when... |
|---|---|
| Attack | No tools defined — scenarios are capability-generic |
| Behavior | No grounding context — falls back to generic user archetypes |
| Persistence | No explicit restrictions in system prompt or implementation code |

Surface these gaps to the user if relevant.
