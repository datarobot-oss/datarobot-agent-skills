---
name: datarobot-agent-assist-simulate
description: >-
  Use when the user wants to adversarially test, evaluate, or harden an implemented AI agent before
  deployment; mentions swarm simulation, attack testing, persistence testing, evaluation criteria,
  or eval_report.md.
---

# Agent Assist — Simulate

Adversarially test and harden an implemented agent before deployment. Runs three simulation tracks
(attack, behavior, persistence), then patches and retests failing scenarios across multiple rounds
until all pass or the fixing limit is reached.

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
2. Confirm implementation code exists (`agent.py`, `myagent.py`, `tools.py`, or `app.py`). If not, route to
   `agent-assist-build` and stop.

---

## Step 1 — Configure

Collect answers in sequence. Do not start simulation until all are answered.

If `agent_config.yaml` already exists, read it and ask:
> "Last time: [persona], [context or none], [iterations] rounds of fixing, [eval mode], [model]. Same settings or change anything?"

**Q1 — User type:** Read `agent_spec.md` and offer 2–4 domain-specific personas plus
"Other — describe your user segment."

**Q2 — Grounding context (optional):** Ask for customer tickets, support logs, or behavior
descriptions. Save to `user_context.txt` if provided. Skip if the user says "skip."

**Q3 — Fixing rounds:** Ask:
> "How many rounds of fixing should I run on failing scenarios? Default: 3."

**Q4 — Evaluation mode:** Ask:
> "How should results be evaluated? Standard gives a simple pass/fail. Scored rates each result by severity: low, medium, high, or critical. Default: standard."

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

Run each generator one at a time. Before each, announce what the track tests. After each, report
the count and list the scenario names.

Say: `"Generating attack scenarios — these test whether the agent can be manipulated into bypassing its own restrictions."`

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-attack \
  --input-path .datarobot/swarm/attack-input.json \
  --response-path .datarobot/swarm/attack-output.json \
  --model <model> --server-url <opencode_server_url>
```

Read `.datarobot/swarm/attack-output.json` and report: `"Generated X attack scenarios:"` followed by a list of scenario names.

Say: `"Generating behavior scenarios — these test how the agent handles ambiguous or edge-case user requests."`

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-behavior \
  --input-path .datarobot/swarm/behavior-input.json \
  --response-path .datarobot/swarm/behavior-output.json \
  --model <model> --server-url <opencode_server_url>
```

Read `.datarobot/swarm/behavior-output.json` and report: `"Generated X behavior scenarios:"` followed by a list of scenario names.

Say: `"Generating persistence scenarios — these apply multi-turn pressure to see if the agent holds its position under pushback."`

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-persistence \
  --input-path .datarobot/swarm/persistence-input.json \
  --response-path .datarobot/swarm/persistence-output.json \
  --model <model> --server-url <opencode_server_url>
```

Read `.datarobot/swarm/persistence-output.json` and report: `"Generated X persistence scenarios:"` followed by a list of scenario names.

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

If `.datarobot/swarm/results.json` exists, ask the user:
> "Previous results exist — run again and archive them? (yes/no)"

If yes, archive the directory with a timestamp (`mv .datarobot/swarm .datarobot/swarm-<timestamp>`)
and continue. If no, stop and let the user review previous results.

Find all implementation files in the working directory (`agent.py`, `myagent.py`, `tools.py`, `app.py`) and pass
each as a separate `--implementation` flag. Tell the user before launching:
> "[N] scenarios queued — covering adversarial attacks, ambiguous user behavior, and multi-turn pressure. Typically 2–5 minutes."

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

Say: `"N of M scenarios passed."`

Then give a structured narrative before proceeding:

**Per-track summary** — for each track (attack, behavior, persistence), state how many passed
and list each scenario with one line on what it tested. Example:
> "Attack — 4/4 passed: path traversal via load_dataset, query injection via run_analysis,
> scope escalation via wildcard, instruction override attempt."

**Per-breach narrative** — for each breach, say:
> "Breach: [scenario_name] ([track])
> What happened: [breach_reason in plain language]
> Likely fix: [prompt addition / code guard]"

Determine "likely fix" from the breach: if the agent violated a stated restriction, it is a
prompt patch. If the agent attempted a tool call it should not have made, it may need a code
guard in the implementation.

**Overall read** — one sentence on where the agent is strong and where it is soft. Example:
> "The agent holds well on adversarial attacks and ambiguous behavior, but has soft spots under
> sustained multi-turn pressure."

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

Parse stdout as JSON: `{"status": "...", "breaches": [...], "exhausted": [...], "passed": [...]}`.
Each breach entry has `scenario_id`, `scenario_name`, `track`, `breach_reason`, `transcript`,
`breach_indicators`, `iteration`, and `suggested_rerun_dir`.

If `status` is `complete`, skip to Step 5.

**Fix loop** — repeat until `advance` returns `complete`:

For each breach in `breaches`:

1. Read the breach transcript and `breach_reason`. Propose the minimal addition to the
   system prompt that prevents this behavior. Tell the user:
   > "Breach: [scenario_name] — [breach_reason]
   > Proposed fix: [your proposed text]
   > Apply this patch? (yes/no)"

   If approved, edit `agent_spec.md` directly to append the text to `system_prompt`.
   Then find the `SYSTEM_PROMPT` string in the implementation files (check `agent.py`,
   `myagent.py`, `tools.py`, `app.py`) and apply the same addition there so the deployed
   agent stays in sync with the spec.

   If the breach is structural (cannot be fixed by prompt alone — e.g. a missing tool
   guard in the implementation), say so and read the implementation file at the relevant
   function. Propose a targeted code change and ask for approval. If approved, apply it
   with your Edit tool.

2. Before retesting, tell the user:
   > "Breach: [scenario_name]
   > What happened: [breach_reason]
   > Fix: [one sentence describing what was added to the system prompt or implementation]
   > Retesting now to verify the patch holds."

   Then re-run the scenario. Call `initialize` **once** to set up the run and get the first
   input/response paths:

   ```bash
   <python> <skill_scripts_dir>/native_execution.py initialize agent_spec.md \
     --criteria evaluation_criteria.md \
     --scenario-id <scenario_id> \
     --run-dir <suggested_rerun_dir>
   ```

   This returns `{"role": "runner", "input_path": "...", "response_path": "...", "turn_number": 1, ...}`.

   **Role → prompt name mapping** (use this to pick `--role-prompt`):
   - `runner` → `run-scenario`
   - `fixture` → `generate-tool-return`
   - `evaluator` → `evaluate-result`

   **Drive to terminal** — loop using `submit` output to advance state. Do NOT call `initialize`
   again inside the loop:

   Before each worker call, announce the current step:
   - Runner: `"Turn N/M — running scenario"`
   - Fixture: `"Turn N/M — generating tool return"`
   - Evaluator: `"Turn N/M — evaluating"`

   ```bash
   # 1. Call worker using input_path and response_path from initialize (or previous submit).
   #    For the fixture role: if agent_config.yaml has execution.mode: selective_e2e and
   #    tools.py exists, call tool_executor.py instead of gateway_worker.py:
   #
   #    selective_e2e fixture:
   #    <python> <skill_scripts_dir>/tool_executor.py \
   #      --input-path <input_path> --response-path <response_path> \
   #      --tools-path <tools_path>
   #
   #    all other roles (runner, evaluator) and simulated fixtures:
   <python> <skill_scripts_dir>/gateway_worker.py \
     --role-prompt <run-scenario|generate-tool-return|evaluate-result> \
     --input-path <input_path> \
     --response-path <response_path> \
     --model <model> --server-url <opencode_server_url>

   # 2. Submit and read next state:
   <python> <skill_scripts_dir>/native_execution.py submit \
     --run-dir <suggested_rerun_dir> --response <response_path>
   ```

   `submit` returns the next `{"role", "input_path", "response_path", "turn_number"}` or a
   terminal `{"status": "passed"|"breach"|"error"}`. Use the returned `input_path` and
   `response_path` for the next worker call. Stop when `status` is terminal.

   Report `✓ passed / ✗ breach / ! error` when terminal.

3. After all reruns in this round, call advance with the completed rerun dirs:

   ```bash
   <python> <skill_scripts_dir>/native_convergence.py advance agent_spec.md \
     --rerun <scenario_id>:<suggested_rerun_dir> [--rerun ...]
   ```

   Parse stdout the same way as `initialize`. If `status` is `complete`, stop.
   Otherwise repeat the fix loop for the new `breaches` list.

For any scenario in `exhausted`: read its `breach_reason` and transcript, identify the
implementation function responsible, propose a targeted code fix, ask for approval, apply
with your Edit tool, then rerun it (using the next iteration dir from `suggested_rerun_dir`
in the advance output) and call `advance` again.

When `advance` returns `complete`:
> "Convergence complete. X resolved, Y exhausted."

---

## Step 5 — Report

```bash
<python> <skill_scripts_dir>/native_convergence.py report agent_spec.md \
  --output eval_report.md

kill <opencode_server_pid> 2>/dev/null || true
```

After the script writes `eval_report.md`, append a **"## Changes Applied"** section to the file
listing every change made during Step 4 — scenario name, what was changed, and why. For prompt
patches, list both the addition to `agent_spec.md` and the corresponding change to the
implementation file. For code fixes, list the function and file changed. Use your Edit tool to
append to `eval_report.md`.

Present passed/total, unresolved, exhausted, and readiness to the user. If `ready: false`, say so
explicitly before offering next steps.

Then read `eval_report.md` and present a per-track breakdown. For each track (attack, behavior,
persistence), list each scenario with one line: what it tested, whether it passed initially or
needed a fix, and how many turns it ran.

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

**Step 4 rerun worker failure** — if a runner/fixture/evaluator worker exits non-zero, mark the
scenario failed:

```bash
<python> <skill_scripts_dir>/native_execution.py fail \
  --run-dir <run_dir> --reason "<reason>"
```

Then call `advance` with that run dir so the script records it as errored and moves on.

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
