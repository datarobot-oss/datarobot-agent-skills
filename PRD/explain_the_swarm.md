# How the Native Swarm Simulation Works

## What It Does

Before you deploy an AI agent, this system adversarially tests it. It generates attack, behavior,
and persistence scenarios specific to your agent, runs the agent through each one using isolated
LLM instances, and produces a verdict on whether the agent holds its safety boundaries.

---

## Three Players

**The Harness** is the outer Claude instance running the skill. It talks to the user, runs shell
commands, and spawns subagents. It is the only orchestrator — nothing else controls flow.

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

Python initializes one isolated run directory per confirmed scenario and returns a task list.
The harness owns the execution loop from this point.

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

When all scenarios are terminal, Python aggregates: validates every confirmed scenario has a
result, checks no run is still active, and writes `.datarobot/swarm/results.json`.

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
├── attack-input.json          # generator input packages
├── behavior-input.json
├── persistence-input.json
├── <role>-output.json         # raw generator responses
├── candidates.json            # reviewed scenario proposals
├── runs/
│   └── scn_<id>/
│       ├── run-state.json     # working state for one scenario
│       ├── runner-input.json  # current runner input package
│       ├── fixture-input.json # current fixture input package
│       ├── evaluator-input.json
│       ├── worker-output.json # last raw worker response
│       └── result.json        # terminal ScenarioResult
└── results.json               # aggregate SwarmResults envelope

evaluation_criteria.md         # confirmed scenarios with stable IDs (public)
agent_config.yaml              # versioned simulation config (public)
eval_report.md                 # convergence and patch audit (M7, public)
```
