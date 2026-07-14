# How the Native Swarm Simulation Works

## What It Does

Before you deploy an AI agent, this system adversarially tests it. It generates attack, behavior,
and persistence scenarios specific to your agent, runs the agent through each one using isolated
LLM instances, and produces a verdict on whether the agent holds its safety boundaries.

---

## Three Players

**The Harness** is the outer Claude instance running the skill — the one the user is talking to.
It talks to the user, runs shell commands, and spawns subagents. It is the only orchestrator —
nothing else controls flow.

**Python scripts** are deterministic CLI tools the harness invokes via Bash. No LLM inside them.
They validate untrusted subagent output, advance execution state, manage files, and enforce
contracts. Fast and always produce the same output for the same input.

**Subagents** are fresh Claude instances spawned for a single role. Each receives a role prompt
and a minimal JSON input package. Each returns exactly one structured JSON response and exits.
They never share context with each other or with the harness conversation.

---

## Two Execution Mechanisms

```
Harness calls Python   →   Bash tool   →   deterministic, instant, no LLM
Harness spawns worker  →   Agent spawn →   fresh LLM instance, one response
```

Python is never a subagent. Subagents never run Python. The harness uses both tools alternately
throughout the execution loop.

---

## Key Terms

**Track** — the category of adversarial test. Three tracks exist:
- `attack` — tries to misuse tools to bypass scope or exfiltrate data
- `behavior` — probes edge cases: ambiguous requests, contradictions, unusual user intent
- `persistence` — applies sustained social pressure to get the agent to violate its restrictions

**Scenario** — one specific adversarial test case. Has a name, a track, a list of user turns
(the messages the simulated user sends), expected safe behavior, and breach indicators (signs the
agent has failed). Scenarios are confirmed by the user before any simulation runs.

**scenario_id** — a stable 12-character hex string derived from the scenario's content
(`scn_a3f9c1...`). Used as a stable directory name and reference throughout the system.
Content-derived so it's reproducible from the same scenario definition.

**Fixture** (`ToolFixture`) — a fake tool return value. When the simulated agent calls a tool,
no real tool runs. The fixture provider subagent generates realistic-looking return data so the
agent can continue the conversation as if the tool worked.

**Runner** — a subagent playing the role of the agent being tested. It receives a user turn
and the conversation history, and responds with either a text reply or a tool call — one action
at a time.

**RunnerAction** — the single structured JSON a runner subagent returns. Either
`{"type": "assistant_response", "content": "..."}` or
`{"type": "tool_call", "tool_call": {"tool_name": "...", "args": {...}}}`. One and only one
action per runner invocation.

**Evaluator** — a subagent that reads the completed transcript and decides whether the agent
breached its safety boundaries. It receives the confirmed breach indicators, full transcript, all
tool calls attempted, and fixture history. It returns a verdict: `passed` or `breach`, with
severity and specific evidence.

**run-state.json** — the durable working file for one scenario. Tracks which role is expected
next, how many turns have run, the accumulated transcript, all tool calls attempted, fixture
history, and the final result when terminal. Written by Python after every validated step.

**runner-input.json / fixture-input.json / evaluator-input.json** — the isolated input package
written for the next subagent. The harness reads the path from Python's output and feeds the
file's contents directly to the spawned subagent. The subagent sees only this file and its role
prompt.

**worker-output.json** — the raw JSON response the harness writes after a subagent finishes.
Python reads this file on the next `submit` call to validate and apply the response.

**initialize** (`native_execution.py initialize`) — sets up one scenario for execution. Creates
the `run-state.json` and the first `runner-input.json`. Returns the path the harness should give
to the first runner subagent.

**submit** (`native_execution.py submit`) — validates one worker's response, advances state,
and writes the next input package. Returns either the next role and input path (keep going) or a
terminal result (done). This is the only way state advances — Python, never the harness directly.

**fail** (`native_execution.py fail`) — called by the harness when a worker's output was
malformed twice and there's no point retrying. Records a terminal error result without overwriting
any valid intermediate state.

**SwarmTask** — a harness work item returned by `native_swarm.py prepare`. Contains the
`scenario_id`, the `run_dir` path, the expected `role`, the `input_path` to give the subagent,
and the `response_path` where the harness should write the subagent's output. The harness drives
the loop entirely from these four fields.

**SwarmPreparation** — the envelope returned by `native_swarm.py prepare`. Contains the full
list of `SwarmTask` objects plus any warnings (e.g., a declared tool not found in implementation
code).

**SwarmResults** — the final aggregate written to `.datarobot/swarm/results.json` after all
scenarios are terminal. Contains the ordered list of `ScenarioResult` objects, one per confirmed
scenario.

**ScenarioResult** — the terminal record for one scenario. Contains the final `status`
(`passed`, `breach`, `error`, or `exhausted`), the full transcript, all tool calls, all fixtures,
evaluator severity and evidence, and optionally the structural diagnosis if the breach survived
convergence.

**effective_max_turns** — the turn limit actually applied to a scenario, computed as
`min(scenario.max_turns, config.turn_limits.for_track(track))`. Capped at prepare time so the
harness loop doesn't need to know about config.

**canonical JSON** — a deterministic serialization used to compare tool call arguments.
`json.dumps(sort_keys=True, separators=(",",":"))`. Means `{"a": 1, "b": 2}` and
`{"b": 2, "a": 1}` are the same, but `{"n": 1}` and `{"n": 1.0}` are not — numeric type is
preserved exactly.

**judge_mode** — how the evaluator interprets severity. `standard`: any breach is a breach.
`scored`: only breaches at or above the configured `fail_on` severity levels (e.g., `high`,
`critical`) count as failures; lower-severity findings are recorded but don't block readiness.

**FixProposal** — a fixer subagent's structured output. Contains a `system_prompt_patch` (text
to append to the system prompt), reasoning, and the list of `addresses_scenarios` it claims to
fix.

**StructuralDiagnosis** — a diagnoser subagent's output for a breach that survived convergence.
Contains `remaining_risk` (what the patch couldn't fix), `structural_recommendation` (what code
change is needed), and optionally `function_hint` (the function name to change).

**ConvergenceTask** — a harness work item returned by the convergence CLI. Like `SwarmTask` but
for fixer and diagnoser roles. Contains a `task_id` (`fix_<12hex>` or `diag_<12hex>`), the `role`,
the list of `scenario_ids` it covers, the `input_path` to give the subagent, and the
`response_path` where the harness writes the subagent's output.

**ConvergencePreparation** — the envelope returned by every convergence CLI call
(`initialize`, `advance`, `fail`). Contains a `status` (one of `awaiting_fixers`, `rerunning`,
`awaiting_diagnosers`, `complete`), the `state_path`, and the list of `tasks` for the current
wave. When `status` is `complete`, `tasks` is empty and convergence is done.

**NativeConvergenceState** — the full convergence state persisted to
`.datarobot/swarm/convergence/state.json`. Python reads and writes this file atomically. It holds
the current system prompt, all scenario results, per-scenario iteration counts, all applied patches,
all worker failures, the spec hash guard values, and rerun directory paths. The harness never reads
or writes this file directly.

**PromptPatchRecord** — the audit record written for each successful fixer wave. Contains the
cluster ID, iteration number, timestamp, fixer description and reasoning, the exact patch text
appended, the scenario IDs it addressed, and SHA-256 hashes of the system prompt before and after.
Stored in `state.json` and rendered in `eval_report.md`.

**ConvergenceFailure** — written when a fixer or diagnoser worker fails permanently (two rejected
responses, timeout, or harness calling `native_convergence.py fail`). Records the `task_id`,
`role`, affected `scenario_ids`, failure reason, and timestamp. Scenarios whose fixer failed
remain as `breach` permanently and block `ready: true`.

**NativeReportSummary** — the machine-readable JSON printed by `native_convergence.py report`.
Contains `ready` (bool), `total`, `passed`, `breached`, `exhausted`, `errored`,
`convergence_failures`, `patches_applied`, and `report_path`. The harness uses `ready` as the
authoritative readiness signal — it never infers readiness from the counts itself.

**iteration_counts** — a dict in `NativeConvergenceState` mapping each `scenario_id` to the
number of fixer iterations that have been attempted against it. When this count reaches
`max_iterations`, the scenario is promoted to `exhausted` and handed to a diagnoser.

---

## Phase 1 — Scenario Generation

Python builds three isolated input packages from the agent spec. The harness spawns three
generator subagents in parallel:

| Track | Input | Purpose |
|---|---|---|
| Attack | system prompt + tool schemas | Tool misuse: scope bypass, exfiltration |
| Behavior | system prompt + user persona + examples + grounding context | Edge cases: ambiguity, contradiction |
| Persistence | system prompt + tool schemas + **implementation code** | Restriction bypass under pressure |

Persistence receives implementation code because the generator needs to see where restrictions
are enforced in code, not just stated in the system prompt. A soft implementation creates
different attack surfaces than a hard one.

Python validates all three outputs (rejecting wrong-track responses), presents candidates to the
user for review, then writes `evaluation_criteria.md` with stable content-derived scenario IDs.

---

## Phase 2 — Swarm Execution

`native_swarm.py prepare` reads `evaluation_criteria.md` and `agent_config.yaml`, calls
`native_execution.py initialize` for every confirmed scenario, and returns a flat list of
`SwarmTask` objects. The harness owns the execution loop from this point.

For each scenario the harness runs this cycle, with at most five scenarios concurrently:

```
[harness] spawn runner subagent
          ↓ RunnerAction (tool_call or assistant_response)
[python]  submit → validate response, advance state, write next input
          ↓ {role: "fixture"} or {role: "evaluator"} or {role: "runner"}
[harness] spawn next role
```

**Runner** receives the current user turn, system prompt, tool schemas, accumulated transcript,
and fixture history. It does not receive `expected_safe_behavior` or `breach_indicators` — it
does not know it is being tested.

**Fixture provider** receives the attempted tool call and minimal scenario context (name,
capability target, current user turn). It generates realistic return data. It does not receive
the system prompt or evaluation criteria.

**Evaluator** receives the confirmed breach indicators, full recorded transcript, all attempted
tool calls, and fixture history. It returns a verdict with severity and specific evidence.
A breach without evidence is rejected.

Python enforces at each `submit` call:
- The response matches the expected role and schema
- Fixture args match the attempted call exactly (canonical JSON — `1` vs `1.0` is a mismatch)
- Tool calls to unknown tools go directly to the evaluator as evidence, no fixture spawned
- More than five tool calls in one turn is an execution error, never a pass

On malformed output the harness retries the same role once with the validation reason appended.
On second failure it calls `native_execution.py fail`, which writes a terminal error result.

When all scenarios are terminal, `native_swarm.py aggregate` validates every confirmed scenario
has a result, checks no run is still active, and writes `.datarobot/swarm/results.json`.

---

## Phase 3 — Convergence

Convergence tries to fix breached scenarios by iteratively patching the system prompt, then
diagnoses any that couldn't be fixed. It runs entirely after Phase 2 and never reruns the full
swarm from scratch.

```
native_convergence.py initialize  →  wave of ConvergenceTasks (fixers or diagnosers)
                                      ↓
[harness] spawn fixer/diagnoser subagents  →  write response_path
                                      ↓
native_convergence.py advance     →  validates wave, applies patches, starts reruns
                                      ↓
[harness] run rerun scenarios through the Phase 2 loop
                                      ↓
native_convergence.py advance     →  promotes exhausted to diagnosers or finishes
                                      ↓  (repeat until status == complete)
native_convergence.py report      →  renders eval_report.md, returns NativeReportSummary
```

**Fixer wave** — `initialize` clusters related breaches by track + capability + normalized breach
reason. Each cluster becomes one `ConvergenceTask` (role `fixer`). A fixer subagent receives the
last 3 transcript entries from each affected scenario, the current system prompt, and all prior
patches. It returns a `FixProposal`. Python validates all fixers in the wave atomically — if any
is invalid, no patches are applied. On success, each patch is appended to the system prompt and
written as a `PromptPatchRecord`.

**Rerun wave** — after patches are applied, every scenario that was in the fixer's cluster gets a
rerun. The rerun uses the patched system prompt and pre-seeds fixture history from the prior run.
Reruns use the same Phase 2 runner → fixture → evaluator loop, isolated in
`convergence/runs/<scenario_id>/iteration-<n>/`.

**Diagnoser wave** — scenarios that hit `max_iterations` or whose fixers failed become `exhausted`.
Each gets one `ConvergenceTask` (role `diagnoser`). A diagnoser subagent reads the full transcript,
all patches, and the final system prompt. It returns a `StructuralDiagnosis` that Python attaches
to the `ScenarioResult`. These diagnoses surface in `eval_report.md` as implementation-level
recommendations requiring user approval.

**Spec hash guard** — `initialize` records a SHA-256 hash of `agent_spec.md`. Every subsequent
`advance` and `fail` call re-hashes the file and rejects the call if the hash changed. This
prevents external edits from silently corrupting the convergence state.

**Atomicity** — Python validates every response in a wave before mutating any state. A single
invalid fixer or diagnoser response aborts the entire wave without touching `agent_spec.md`,
`state.json`, or any rerun directory.

---

## Role Isolation Summary

| Role | Sees | Does not see |
|---|---|---|
| Generator | Spec, tools, implementation (persistence only) | Other generators' output |
| Runner | System prompt, tools, transcript, fixture history | Expected behavior, breach indicators |
| Fixture provider | Tool schema, attempted call, scenario name + turn | System prompt, evaluation criteria |
| Evaluator | Confirmed criteria, transcript, tool calls, fixtures | System prompt, runner reasoning |

---

## Why Python Owns Validation

Subagent output is untrusted. A runner could hallucinate an extra field, a fixture could silently
alter the arguments it claims to echo, an evaluator could return a breach with no evidence.
Python catches all of this before it touches state. The harness never inspects subagent output
directly — it only acts on what Python confirms is valid.

---

## File Layout

```
.datarobot/swarm/
├── attack-input.json          # generator input packages (Phase 1)
├── behavior-input.json
├── persistence-input.json
├── <role>-output.json         # raw generator responses
├── candidates.json            # reviewed scenario proposals before confirmation
├── runs/
│   └── scn_<id>/              # one directory per confirmed scenario
│       ├── run-state.json     # working state: transcript, fixtures, turn index, next role
│       ├── runner-input.json  # current input package for the runner subagent
│       ├── fixture-input.json # current input package for the fixture provider
│       ├── evaluator-input.json
│       ├── worker-output.json # last raw worker response (overwritten each turn)
│       └── result.json        # terminal ScenarioResult (written once, never overwritten)
└── results.json               # aggregate SwarmResults envelope (written by aggregate)
convergence/
│   ├── state.json             # full NativeConvergenceState — owned by Python, never touched by harness
│   ├── fixers/
│   │   └── fix_<12hex>/
│   │       ├── input.json     # fixer subagent input package (breached transcripts, current prompt, prior patches)
│   │       └── response.json  # harness writes fixer subagent's raw response here
│   ├── diagnosers/
│   │   └── <scenario_id>/
│   │       ├── input.json     # diagnoser subagent input package (full transcript, patches, final prompt)
│   │       └── response.json
│   └── runs/
│       └── <scenario_id>/
│           └── iteration-<n>/ # isolated rerun directory — same layout as .datarobot/swarm/runs/

evaluation_criteria.md         # confirmed scenarios with stable IDs (user-visible)
agent_config.yaml              # versioned simulation config (user-visible)
eval_report.md                 # convergence and patch audit (user-visible)
```
