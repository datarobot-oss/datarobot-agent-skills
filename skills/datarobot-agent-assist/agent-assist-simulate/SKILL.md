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
- `<skill_prompts_dir>` is `<this_skill_dir>/prompts/`.
- Confirm both directories exist. If either is missing, tell the user the skill installation is incomplete and stop.
- Use resolved absolute paths for every scripts or prompts reference in this skill.

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

If dependency installation or the version check still fails, surface the error and stop. Simulated
native execution does not require DataRobot credentials.

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

If `agent_config.yaml` already exists, present its persona, grounding path, convergence iterations,
and evaluation mode:
> "Last time: [persona], [context or no context], [iterations] iterations, [evaluation mode].
> Same settings or change anything?"

After collection, persist the native configuration:

```bash
<python> <skill_scripts_dir>/native_scenarios.py configure agent_spec.md \
  --user-persona "<persona>" \
  --iterations <n> \
  --judge-mode <standard|scored> \
  [--context user_context.txt]
```

Do not ask for a model. Use the active harness model. Capture its identifier later only when the
harness exposes reliable model metadata; otherwise leave it unknown.

---

## Step 2 — Generate and Review Scenarios

Prepare isolated input packages:

```bash
<python> <skill_scripts_dir>/native_scenarios.py prepare agent_spec.md \
  --config agent_config.yaml
```

Spawn three fresh native subagents in parallel:

- Attack: `<skill_prompts_dir>/generate-attack.md` with `.datarobot/swarm/attack-input.json`
- Behavior: `<skill_prompts_dir>/generate-behavior.md` with `.datarobot/swarm/behavior-input.json`
- Persistence: `<skill_prompts_dir>/generate-persistence.md` with
  `.datarobot/swarm/persistence-input.json`

Each subagent receives only its role prompt and input JSON. It must return only the required JSON
object. Save the exact objects to `.datarobot/swarm/<role>-output.json`, then validate them:

```bash
<python> <skill_scripts_dir>/native_scenarios.py finalize
```

If validation fails, stderr identifies each failed role as
`role:<role> validation failed: <reason>`. Retry each failed role once with a fresh subagent and the
same input JSON. Append this exact note to its role prompt:
`Your previous response was rejected: <reason>. Correct the response and try again.`
Replace only that role's output file and run `finalize` again. If any role still fails, surface the
error and stop.

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

Prepare all confirmed scenarios:

```bash
<python> <skill_scripts_dir>/native_swarm.py prepare agent_spec.md \
  --criteria evaluation_criteria.md \
  --config agent_config.yaml \
  --implementation <path> [--implementation <path> ...]
```

Treat stdout as a `SwarmPreparation` JSON object. Surface its warnings. The harness owns an
in-memory task queue and runs at most five worker invocations concurrently. Only one task for a
given `run_dir` may be active at a time; Python never schedules workers.

For each task, spawn a fresh leaf subagent with only the role prompt and the JSON object read from
`input_path`:

- `runner` → `<skill_prompts_dir>/run-scenario.md`
- `fixture` → `<skill_prompts_dir>/generate-tool-return.md`
- `evaluator` → `<skill_prompts_dir>/evaluate-result.md`

Do not pass parent-chat history, sibling output, credentials, or evaluation criteria to a runner.
Save the worker's exact JSON object to the declared `response_path`, then submit it:

```bash
<python> <skill_scripts_dir>/native_execution.py submit \
  --run-dir <run_dir> \
  --response <response_path>
```

If submit returns `status: next`, enqueue the returned task. If it returns a terminal status, report
that scenario's progress and do not enqueue another task for it.

On worker-output validation failure, retry that role once with a fresh subagent and the exact same
input JSON. Append:
`Your previous response was rejected: <reason>. Correct the response and try again.`
Overwrite only the declared response file and submit again. After a second rejection, timeout, or
worker unavailability, record the terminal failure:

```bash
<python> <skill_scripts_dir>/native_execution.py fail \
  --run-dir <run_dir> \
  --reason "<reason>"
```

When every scenario is terminal, aggregate:

```bash
<python> <skill_scripts_dir>/native_swarm.py aggregate agent_spec.md \
  --criteria evaluation_criteria.md \
  --config agent_config.yaml \
  --output .datarobot/swarm/results.json
```

---

## Step 4 — Converge

Initialize native convergence. Pass `--actual-model` only when the harness exposes reliable model
metadata; never guess it.

```bash
<python> <skill_scripts_dir>/native_convergence.py initialize agent_spec.md \
  --criteria evaluation_criteria.md \
  --config agent_config.yaml \
  --results .datarobot/swarm/results.json \
  [--actual-model "<active-model>"]
```

Process each returned task wave in bounded batches of at most five:

- `fixer` → `<skill_prompts_dir>/generate-fix.md`
- `diagnoser` → `<skill_prompts_dir>/diagnose-failure.md`
- `runner`, `fixture`, or `evaluator` → the Step 3 scenario-execution loop

For fixer and diagnoser tasks, give a fresh leaf subagent only its role prompt and declared input
JSON, then save its exact JSON object to `response_path`. After every fixer/diagnoser wave, or after
all returned rerun scenarios become terminal, advance:

```bash
<python> <skill_scripts_dir>/native_convergence.py advance agent_spec.md
```

`advance` validates the whole wave before applying prompt patches. Prompt patches are automatic and
audited; structural implementation changes are not.

On invalid fixer/diagnoser output, retry only that task once using the exact input and rejection note
from Step 3. After a second rejection, timeout, or worker unavailability:

```bash
<python> <skill_scripts_dir>/native_convergence.py fail agent_spec.md \
  --task-id <task_id> \
  --reason "<reason>"
```

Continue from the tasks returned by `advance` or `fail` until status is `complete`.

## Step 5 — Report and Optional Structural Fixes

Render the authoritative report:

```bash
<python> <skill_scripts_dir>/native_convergence.py report agent_spec.md \
  --output eval_report.md
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
