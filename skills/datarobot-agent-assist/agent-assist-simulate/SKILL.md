---
name: datarobot-agent-assist-simulate
description: >-
  Use when the user wants to adversarially test, evaluate, or harden an implemented AI agent before
  deployment; mentions swarm simulation, attack testing, persistence testing, evaluation criteria,
  or eval_report.md.
---

# Agent Assist — Simulate

Use this workflow to adversarially test an implemented agent before deployment.

This workflow reads `agent_spec.md` and any generated code (`tools.py`, `agent.py`) to run three
tracks of automated simulation, then iteratively hardens the agent through a convergence loop —
patching the system prompt automatically and, where prompt patching isn't sufficient, diagnosing
structural issues and offering targeted code fixes for user approval. All configuration is
collected through conversation before anything runs.

---

## Script Path Resolution

Before invoking the simulation script, resolve `<skill_scripts_dir>` once for the session:

- This `SKILL.md` file was loaded from a known path. Take that path, strip the filename, and that directory is `<this_skill_dir>`.
- `<skill_scripts_dir>` is `<this_skill_dir>/scripts/`.
- Confirm the directory exists. If missing, tell the user the skill installation is incomplete and stop.
- Use the resolved absolute path for every `<skill_scripts_dir>/...` reference in this skill.

**Python and dependency check (run once before the first script call):**

Resolve the Python binary to use — in order of preference:
1. If a `.venv/` directory exists in the working directory, use `.venv/bin/python3`
2. Otherwise use `python3`

Store the resolved binary as `<python>` and use it for all script calls.

Require Python 3.11 or newer and the deterministic script dependencies:
```bash
<python> -c "import sys; assert sys.version_info >= (3, 11)"
<python> -c "import pydantic, yaml" 2>/dev/null \
  || uv pip install pydantic pyyaml \
  || <python> -m pip install pydantic pyyaml
<python> -c "import pydantic, yaml"
```

If dependency installation or the version check still fails, surface the error and stop.

**OpenCode check (run once before Step 1):**

```bash
opencode --version 2>/dev/null
```

If this fails, install OpenCode and update PATH for this session:

```bash
dr opencode upgrade
export PATH="$PATH:$HOME/.opencode/bin"
opencode --version
```

If it still fails after install, tell the user and stop — all worker invocations require OpenCode.

**DataRobot authentication check (run once before Step 1):**

```bash
dr auth check
```

If this fails, tell the user to run `dr auth login` and retry. Do not proceed without valid
credentials — all worker invocations require authenticated LLMGateway access.

---

## Pre-flight Check

1. Confirm `agent_spec.md` exists in the working directory. If not, tell the user and stop —
   this workflow requires a completed spec. Offer to switch to `agent-assist-build` to build one.
2. Confirm the spec has a `system_prompt`. If missing, surface the gap and stop. Agents without
   tools are valid, but their attack coverage is capability-generic.
3. Confirm implementation code exists in `agent.py`, `tools.py`, or `app.py`. If none exists, route
   the user to `agent-assist-build` and stop. Note existing files as potential structural-fix targets.

---

## Step 1 — Collect Configuration

Ask the following questions in sequence. Do not run the simulation until all answers are collected.
Save answers to `agent_config.yaml` automatically after collection.

Before creating new internal artifacts, check for `.datarobot/swarm/runs/`,
`.datarobot/swarm/results.json`, or `.datarobot/swarm/convergence/state.json`. If present, archive
the entire `.datarobot/swarm/` directory with a timestamp. Never delete or silently overwrite an
earlier run.

**Question 1 — User type:**

Read `agent_spec.md` and derive 2–4 user personas specific to this agent's domain. Always append "Other — describe your user segment" as the last option:

> "Who are the primary users of this agent?
> 1. [derived persona 1]
> 2. [derived persona 2]
> ...
> N. Other — describe your user segment"

If the user picks "Other", ask: *"Describe your users in a sentence."*

**Question 2 — Grounding context (optional):**
> "Want to ground the behavior scenarios in real user data? Paste customer tickets, support logs,
> or a description of how your users typically behave — or say 'skip' to use defaults."

If the user provides text, save it to `user_context.txt` in the working directory and pass the
path to the script. If they skip, pass no context file.

**Question 3 — Iteration limit:**
> "How many times should I attempt to fix a failing scenario before marking it unresolved?
> Default is 3."

**Question 4 — Evaluation mode:**
> "Standard breach detection (pass/fail) or scored evaluation using an LLM judge?
> Default is standard."

**Question 5 — Simulation model:**

Run `dr opencode models` and present up to six as a numbered list, with the first as the default:

> "Which model should simulation workers use?
> 1. [first model] (default)
> 2. [next model]
> ...
> N. Other — enter a model ID"

Store the chosen model ID as `<model>` for all `gateway_worker.py` calls in Steps 2–4.

**Question 6 — Selective tool execution (optional):**

Read `agent_spec.md` and list every tool whose definition includes `is_readonly: true`. If none are marked readonly, skip this question silently and proceed with fully simulated mode.

If at least one readonly tool exists, ask:

> "I can call these read-only tools for real during simulation instead of generating fictional return values:
> [list each is_readonly tool with its description]
> Run them for real, or simulate all? Default is simulate."

If the user chooses real execution, store the approved tool names as `<e2e_tools>` (a space-separated list) and set `execution.mode` to `selective_e2e` in the persisted config. Otherwise leave `execution.mode` as `simulated`.

If `agent_config.yaml` already exists, read it and present `persona.description`,
`grounding.context_path` (or "no context"), `convergence.max_iterations`, `evaluation.mode`, and
the previously used model:
> "Last time: [persona], [context or no context], [iterations] iterations, [evaluation mode], [model].
> Same settings or change anything?"

**Start the OpenCode server (run once after model selection, before any parallel workers):**

```bash
dr opencode serve --port 4096 2>/dev/null &
until curl -sf http://127.0.0.1:4096/global/health >/dev/null 2>&1; do sleep 0.25; done
```

Store the background process PID as `<opencode_server_pid>` and `http://127.0.0.1:4096` as `<opencode_server_url>`. All `gateway_worker.py` calls in Steps 2–4 must include `--server-url <opencode_server_url>`. One server process owns the SQLite database, so workers never contend on it regardless of parallelism.

After collection, persist the native configuration:

```bash
<python> <skill_scripts_dir>/native_scenarios.py configure agent_spec.md \
  --user-persona "<persona>" \
  --iterations <n> \
  --judge-mode <standard|scored> \
  --model "<model>" \
  [--context user_context.txt]
```

---

## Step 2 — Generate and Review Scenarios

Prepare isolated input packages:

```bash
<python> <skill_scripts_dir>/native_scenarios.py prepare agent_spec.md \
  --config agent_config.yaml
```

Use one global worker queue for every subagent invocation in Steps 2–4. The hard cap is twenty active
workers across generators, scenario roles, convergence roles, and retries combined. As soon as any
worker completes, submit its output and dispatch one new worker into the freed slot. Never wait for
all in-flight workers when one completed worker can be processed; keep slots filled continuously.
Queue retries behind the same cap — never launch an extra retry alongside twenty active workers.

Run three generator workers in parallel via the gateway adapter.
Pass prompt names (not file paths) to `--role-prompt` — the script resolves them automatically:

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-attack \
  --input-path .datarobot/swarm/attack-input.json \
  --response-path .datarobot/swarm/attack-output.json \
  --model <model> \
  --server-url <opencode_server_url>

<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-behavior \
  --input-path .datarobot/swarm/behavior-input.json \
  --response-path .datarobot/swarm/behavior-output.json \
  --model <model> \
  --server-url <opencode_server_url>

<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt generate-persistence \
  --input-path .datarobot/swarm/persistence-input.json \
  --response-path .datarobot/swarm/persistence-output.json \
  --model <model> \
  --server-url <opencode_server_url>
```

Each worker receives only its role prompt and input JSON and writes only the required JSON object
to its response path. Validate all three outputs:

```bash
<python> <skill_scripts_dir>/native_scenarios.py finalize
```

If validation fails, stderr identifies each failed role as
`role:<role> validation failed: <reason>`. Retry each failed role once by rerunning its
`gateway_worker.py` call with `--rejection-note "<reason>"`. Replace only that role's output file
and run `finalize` again. If any role still fails, surface the error and stop.

Present the grouped candidate list printed by `finalize`. Ask:
> "Does this look right? You can say 'add [description]' to include a scenario or 'remove [name]'
> to drop one. Say 'run it' when ready."

Apply conversational additions or removals to `.datarobot/swarm/candidates.json`; every candidate
must retain the documented scenario fields and must not contain `scenario_id`. Do not rerun
generation. When the user confirms, write the authoritative criteria:

```bash
<python> <skill_scripts_dir>/native_scenarios.py confirm --output evaluation_criteria.md
```

---

## Step 3 — Run Simulation

Use native code search to identify the agent entry point and relevant implementation files. Pass
their explicit project-contained paths; do not ask Python to crawl the repository.

Check whether previous simulation results exist:

```bash
ls .datarobot/swarm/runs 2>/dev/null && echo "exists"
```

If the directory exists, ask the user:
> "Previous results exist — running again will overwrite them. Continue?"

If the user confirms, delete the existing runs before proceeding:

```bash
rm -rf .datarobot/swarm/runs
```

Tell the user the scenario count and estimated time before launching:
> "Running \<N\> scenarios across 3 tracks — typically 2–5 minutes."

Then run the full simulation in one command:

```bash
<python> <skill_scripts_dir>/native_swarm.py run agent_spec.md \
  --criteria evaluation_criteria.md \
  --config agent_config.yaml \
  --server-url <opencode_server_url> \
  --model <model> \
  --implementation <path> [--implementation <path> ...] \
  [--tools-path <path/to/tools.py>]
```

Include `--tools-path` only when `execution.mode` is `selective_e2e` and a `tools.py` file exists
in the project. Progress lines stream to stderr as each scenario completes. Parse stdout as the
summary JSON — same shape as `aggregate` output.

Any `warning:` lines on stderr indicate implementation coverage gaps (e.g. a declared tool not found
in the implementation files). Surface each one to the user before presenting results.

**Present results in plain language after the run:**

Lead with the overall outcome:
> "N of M scenarios passed."

If all passed:
> "All N scenarios passed across attack, behavior, and persistence — no issues found."

Otherwise list each breach by track and name:
> "Breached:
> - [track] scenario name
> - ..."

If any errored:
> "N scenario(s) could not be evaluated due to worker errors. Check `.datarobot/swarm/metrics.jsonl` for details."

Then transition naturally:
- If `breached > 0`: *"Found X breach(es). Running the convergence loop to fix them automatically — generating targeted system prompt patches and retesting up to N iterations per scenario."*
- If `breached == 0`: skip Step 4 entirely and go directly to Step 5.

---

## Step 4 — Converge

Initialize native convergence:

```bash
<python> <skill_scripts_dir>/native_convergence.py initialize agent_spec.md \
  --criteria evaluation_criteria.md \
  --config agent_config.yaml \
  --results .datarobot/swarm/results.json \
  --actual-model "<model>"
```

Add each returned task wave to the same global worker queue and process it with the twenty-worker hard
cap. Do not start the next wave until all tasks in the current wave have reached a submitted or
failed terminal transition:

- `fixer` → `--role-prompt generate-fix`
- `diagnoser` → `--role-prompt diagnose-failure`
- `runner`, `fixture`, or `evaluator` → rerun loop below

**Keep user-facing progress conversational:**

- Before a fixer wave, read `breached_scenarios` from each fixer input and the current iteration
  from convergence `state.json`. Announce clearly:
  > "Patching: [scenario name] (attempt 2 of 3)"
- Before reruns, say which scenario is being retested:
  > "Retesting: [scenario name]"
  Then report each terminal outcome as it completes: `[<track>] <scenario_name>  <✓ passed | ✗ breach | ! error>`
- Before a diagnoser wave, announce which scenarios are exhausted and being diagnosed:
  > "Diagnosing unresolved breach: [scenario name] — identifying structural changes needed."
- When `advance` returns `complete`, summarise what happened:
  > "Convergence complete. X breach(es) resolved, Y exhausted after reaching the iteration limit."
  Then transition: *"Generating the evaluation report."*

For fixer and diagnoser tasks, invoke the gateway adapter:

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt <role> \
  --input-path <input_path> \
  --response-path <response_path> \
  --model <model> \
  --server-url <opencode_server_url>
```

Role prompt mapping:
- `fixer` → `generate-fix.md`
- `diagnoser` → `diagnose-failure.md`

**Convergence rerun loop** — for each `runner`, `fixture`, or `evaluator` task returned by `advance`,
drive it to terminal sequentially (reruns are few; parallelism is not required here):

```bash
<python> <skill_scripts_dir>/gateway_worker.py \
  --role-prompt <role_prompt> \
  --input-path <input_path> \
  --response-path <response_path> \
  --model <model> \
  --server-url <opencode_server_url>
```

Role prompt mapping: `runner` → `run-scenario.md`, `fixture` → `generate-tool-return.md`,
`evaluator` → `evaluate-result.md`.

Submit the response and route from the returned transition:

```bash
<python> <skill_scripts_dir>/native_execution.py submit \
  --run-dir <run_dir> \
  --response <response_path>
```

If `submit` returns `role`, dispatch the next role with the returned `input_path` and
`response_path`. If it returns a terminal status, record the outcome. On validation failure
(`role:<role> validation failed: <reason>` in stderr), retry once with `--rejection-note "<reason>"`.
After a second failure:

```bash
<python> <skill_scripts_dir>/native_execution.py fail \
  --run-dir <run_dir> \
  --reason "<reason>"
```

All paths returned by `submit` are absolute — pass them directly without reconstruction. Route
solely from the returned transition; do not read `run-state.json`. the declared `result_path` in a
terminal transition holds the final outcome (`status`).

After every fixer/diagnoser wave, or after all returned rerun scenarios become terminal, advance:

```bash
<python> <skill_scripts_dir>/native_convergence.py advance agent_spec.md
```

`agent_spec.md` is required as the first positional argument. Do not pass `--convergence-dir`;
the default `.datarobot/swarm/convergence` is used automatically. `advance` validates the whole
wave before applying prompt patches. Prompt patches are automatic and
audited; structural implementation changes are not.

On invalid fixer/diagnoser output, retry only that task once by rerunning `gateway_worker.py` with
the exact input and `--rejection-note "<reason>"`. After a second rejection, timeout, or worker
unavailability:

```bash
<python> <skill_scripts_dir>/native_convergence.py fail agent_spec.md \
  --task-id <task_id> \
  --reason "<reason>"
```

Continue from the tasks returned by `advance` or `fail` until status is `complete`.

After the final `advance` returns `complete`, tell the user in plain language before moving to Step 5:
> "Convergence complete. [X] breach(es) resolved by prompt patching, [Y] scenario(s) exhausted after [N] iterations."

Then proceed to Step 5.

## Step 5 — Report and Optional Structural Fixes

Render the authoritative report:

```bash
<python> <skill_scripts_dir>/native_convergence.py report agent_spec.md \
  --output eval_report.md
```

Then shut down the OpenCode server started in Step 1:

```bash
kill <opencode_server_pid> 2>/dev/null || true
```

Use the returned JSON summary as authoritative. Present passed/total, unresolved, exhausted, errored,
convergence-worker failures, patches applied, readiness, and the report path. Do not independently
infer readiness.

If prompt patches were applied, explain that `agent_spec.md` was updated and the complete audit is in
`eval_report.md`.

For every structural diagnosis, present its scenario, remaining risk, recommendation,
`function_hint`, and likely implementation target. Then ask exactly:
> "Would you like me to implement these structural fixes?"

Stop and wait. If declined, leave implementation files unchanged. If approved, locate the hinted
function using native code search, apply only the targeted changes, explain each edit, and offer a
fresh simulation. A missing `function_hint` is guidance for manual target identification, not
permission to make a broad code change.

---

## Simulation Tracks — What Degrades Silently

| Track | Degrades when... |
|---|---|
| Attack | No tools defined — generates generic scenarios with no capability targeting |
| Behavior | No grounding context provided — falls back to generic user archetypes |
| Persistence | System prompt AND implementation code have no explicit restrictions (`only`, `never`, `cannot`, dollar limits) — both are scanned; sparse output only when neither has restrictions |

Surface these gaps to the user if relevant.

---

## After Simulation

If the report returns `ready: false`, state that the evaluation did not fully pass before offering
next steps. Keep Deploy available only with the explicit warning that coverage is incomplete or
failing; never describe the agent as ready.

Offer next steps:

```
What would you like to do next?
1. Review eval_report.md     — outcomes, audit history, and unresolved scenarios
2. Re-run simulation         — after making further changes to the spec or code
3. Test locally              — run the agent on your machine before deploying
4. Deploy                    — deploy the hardened agent to DataRobot
```

- If **1**: read `eval_report.md` and present a structured summary to the user.
- If **2**: return to Step 1 to re-collect configuration (or reuse saved settings) and re-run.
- If **3**: read `AGENTS.md` for the local test command, display it in a code block, tell the user to run it in a new terminal. Do not run it yourself.
- If **4** and `ready` is false: repeat the warning and ask whether the user wants to deploy anyway.
  Stop and wait for confirmation.
- If **4** and the user confirms, or `ready` is true: follow the deploy instructions in
  `agent-assist-build/SKILL.md`.
