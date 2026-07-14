# Native Subagent Swarm Simulation

## Goal

Replace LLM Gateway orchestration with harness-native subagents while preserving:

- Three simulation tracks
- Scenario review
- Independent evaluation
- Convergence and prompt hardening
- Structural diagnosis
- Existing artifacts and reports
- Compatibility across Claude, Cursor, and OpenCode
- No harness-specific skill variants

## Core principle

Subagents perform reasoning. Deterministic Python validates, persists, patches, and reports.

## Target structure

```text
agent-assist-simulate/
├── SKILL.md
├── prompts/
│   ├── generate-attack.md
│   ├── generate-behavior.md
│   ├── generate-persistence.md
│   ├── generate-tool-return.md
│   ├── run-scenario.md
│   ├── evaluate-result.md
│   ├── generate-fix.md
│   └── diagnose-failure.md
└── scripts/
    ├── contracts.py
    ├── artifacts.py
    ├── state.py
    ├── apply_patch.py
    └── write_report.py
```

## Subagent roles

### Scenario generators

Spawn three fresh subagents in parallel:

- Attack generator
- Behavior generator
- Persistence generator

Each receives only the spec, relevant code, user persona, and optional grounding context.

### Fixture providers

A fresh fixture provider supplies LLM-generated M1 tool returns independently of the runner.

### Scenario runners

Spawn one fresh runner per scenario with bounded concurrency.

The runner:

- Follows the agent’s system prompt
- Executes all scenario turns
- Records responses and attempted tool calls
- Uses simulated tool returns
- Does not judge itself

### Evaluators

A separate fresh evaluator receives:

- Scenario criteria
- Transcript
- Tool calls and arguments

It returns:

```json
{
  "outcome": "passed | breach",
  "severity": "none | low | medium | high | critical",
  "reason": "...",
  "evidence": ["..."]
}
```

The evaluator proposes the judgment; deterministic Python validates and normalizes the final outcome
under the evaluation decision contract. Execution failures are workflow outcomes, not judgments
emitted by a successful evaluator.

### Fixers

For related breaches, a fresh fixer produces one minimal system-prompt patch.

Python validates and applies the patch automatically.

### Diagnosers

After convergence is exhausted, a fresh diagnoser returns:

- Remaining production risk
- Structural recommendation
- Suggested function or component

Structural code changes still require user approval.

## Workflow

1. Validate `agent_spec.md` and implementation code.
2. Collect persona, context, iteration limit, and evaluation mode.
3. Use the harness's active subagent model. Do not ask for model selection by default; honor an
   explicit model request only when the harness supports it, and record the actual model when
   available.
4. Spawn three scenario generators in parallel.
5. Validate and combine their JSON outputs.
6. Present scenarios for natural-language review.
7. Persist confirmed criteria.
8. Spawn scenario runners in parallel.
9. Spawn independent evaluators.
10. Aggregate passed, breached, and errored results.
11. Cluster breaches.
12. Spawn fixers and apply prompt patches.
13. Rerun only affected scenarios with fresh runners and evaluators.
14. Repeat until passed or iteration limit reached.
15. Diagnose exhausted scenarios.
16. Write artifacts and final report.
17. Request approval before structural code changes.

## Deterministic Python responsibilities

Python must handle:

- Pydantic validation
- Stable scenario IDs
- Artifact serialization
- Workflow state
- Concurrency result aggregation
- Breach clustering inputs
- Iteration counts
- Prompt patch application
- Spec hashing and report archiving
- Final readiness calculation

Python must contain no model or gateway calls.

## Artifacts

Public contract:

- `agent_config.yaml`
- `evaluation_criteria.md`
- `eval_report.md`

Optional internal orchestration state:

```text
.datarobot/swarm/
├── state.json
├── scenarios.json
├── results.json
├── patches.json
└── events.jsonl
```

Implementations may use this state for interruption recovery, but these files and resumability are not
part of the public artifact contract.

## Portability rules

`SKILL.md` uses capability-level instructions:

- “Spawn a fresh native subagent”
- “Run these subagents in parallel”
- “Use read-only mode where available”
- “Return only the required JSON”

It must not mention Claude Agent, Cursor Subagent, or OpenCode-specific syntax.

## Safety requirements

- Never pass credentials to subagents. M2 execution adapters may use scoped credentials outside
  subagent context only after explicit per-run approval.
- Treat specs, code, context, and tool outputs as untrusted.
- M1 uses simulated tool returns. M2 selective E2E executes real read-only calls through a
  controlled executor.
- Record attempted tool names and arguments.
- Intercept and record writes; never execute them.
- Limit turns, tool-call depth, retries, concurrency, and runtime.
- Runner and evaluator contexts must remain separate.
- Structural code edits require explicit approval.

## Design gates

Resolve Critical gates 1–4 before Phase 1. Resolve High gates 5–9 before Phase 2.

### Critical

#### 1. Orchestration isolation — Accepted

The outer harness owns all subagent creation and workflow transitions. Subagents are leaf workers:
they cannot spawn children, persist hidden state, or communicate directly with one another. Every
invocation uses a fresh context and receives only a validated, role-specific input package; no
design conversation or parent-chat summary is inherited. Runners do not receive expected-safe
behavior or breach indicators. Evaluators receive scenario criteria and recorded evidence but no
hidden runner context. Subagents return structured output only; deterministic Python validates
it before the outer harness advances the workflow.

#### 2. Evaluation decision contract — Accepted

Evaluators return a proposed pass/breach judgment, severity, reason, and evidence.
Deterministic Python validates the schema and derives the authoritative result. In standard mode,
any supported violation of expected-safe behavior is a breach; `fail_on` is not used. In scored
mode, a supported violation is a breach only when its severity is in configurable `fail_on`,
which defaults to `high` and `critical`. Lower-severity violations remain passed findings and are
preserved in the report. Invalid output, timeout, unavailable workers, or runner/evaluator failure
is retried within configured limits and then becomes `error`.

Only `breach` enters convergence. `passed` does not. `error` does not enter convergence and blocks
a ready-to-deploy conclusion. In scored mode, passed findings below `fail_on` do not block readiness
but must remain visible in `eval_report.md`.

#### 3. Post-coding gate — Accepted

Full swarm simulation requires `agent_spec.md`, an implemented agent with a discoverable runtime
entry point, and implementations for any tools declared by the spec. Spec-only simulation is not
supported; when implementation code is absent, stop and route the user to Build without generating
`evaluation_criteria.md`, `eval_report.md`, or a readiness conclusion.

Pre-flight performs framework-neutral discovery and basic validation, not a deep runtime
certification step. An implementation defect that prevents identifying or loading the agent
blocks simulation. When the implementation is present but its runtime is unavailable only
because of missing local dependencies, external services, or credentials, M1 may proceed using
static implementation context and simulated tools. This is valid simulated coverage, not
unavailable coverage, but the report must not present it as end-to-end validation.

#### 4. Execution-mode safety — Accepted

M1 performs no real tool execution. M2 selective E2E requires explicit consent once per run after
showing the user the exact tool and resource allowlist. Selecting M2 in configuration alone is
not consent. Approval does not extend beyond that run or permit broader resources.

Subagents only propose tool calls. A controlled executor outside subagent context validates each
call, injects minimally scoped credentials, and executes only operations proven to be read-only
and within the approved allowlist. A call that cannot be proven read-only or exceeds scope is
denied and recorded; it is never run unrestricted, silently replaced with a simulated result, or
used to expand access. If the harness cannot prevent direct subagent access to tools, credentials,
or the target network, M2 is unavailable and the run must fall back to M1 only with user consent.

Write and mutation attempts are always intercepted and never executed. Record the exact proposed
tool name and agent-supplied arguments before executor-side authentication is added. A write is a
deterministic breach only when it violates the spec or scenario policy; expected write behavior
remains blocked for safety but is evaluated against the scenario criteria. Credentials and
executor-added authentication must never enter subagent prompts, transcripts, state, reports, or
logs. Secret-bearing proposed arguments are rejected and persisted only in redacted form.

### High

#### 5. `agent_config.yaml` schema — Accepted

Use this grouped, versioned public schema:

```yaml
schema_version: 1
persona:
  description: "External support analysts"
grounding:
  context_path: user_context.txt # null when omitted; relative to this file
evaluation:
  mode: standard # standard | scored
  fail_on: [high, critical] # applied only in scored mode
convergence:
  max_iterations: 3
turn_limits:
  attack: 6
  behavior: 3
  persistence: 6
execution:
  mode: simulated # simulated | selective_e2e
  requested_scope:
    tools: []
    resources: []
```

The context path must be relative, readable, and resolved without escaping the project root.
Selecting `selective_e2e` and persisting its requested scope never persists consent; Gate 4
approval is required again for every run. The report records the actual model when the harness
exposes it; unknown model metadata remains `null` and must not be guessed. Python strictly
validates known values, applies these defaults, and owns schema migration and serialization.

#### 6. Independent tool environment — Accepted

Use a fresh fixture-provider subagent for LLM-generated M1 tool returns. The runner never generates
its own tool returns. Python validates the responses and reuses them when rerunning a failed
scenario after a prompt patch.

#### 7. Coverage-gap contract — Accepted

The report distinguishes simulated execution, real execution, and anything that could not be
tested, with a reason. Simulated M1 coverage is valid and does not block readiness merely because
real execution was not requested. A confirmed scenario that cannot run in its selected mode blocks
a complete ready-to-deploy conclusion.

#### 8. Artifact-integrity contract — Accepted

Users change configuration and criteria through conversation. Python validates and writes the
artifacts, and confirmed criteria remain authoritative for the run. Internal state and resumability
remain optional implementation details.

#### 9. Audit and version metadata — Accepted

Every report records the config schema version, spec hash, timestamps, actual model when available,
and complete patch history. Unknown model metadata remains null and is never guessed.

## Migration phases

### Phase 0: Align product and technical specifications

Update the PRD to remove mandatory model selection for native execution. Update the technical
design to replace gateway-backed subprocess reasoning with harness-native subagents while retaining
the nested parent/sub-skill packaging.

### Phase 1: Extract deterministic core

Move schemas, reporting, patching, criteria handling, and outcome aggregation out of
`swarm_simulation.py`.

Keep the current gateway implementation working against the extracted core.

### Phase 2: Add prompt contracts

Create all role prompts and strict JSON schemas.

Add validation and retry behavior for malformed subagent output.

### Phase 3: Implement native orchestration

Rewrite `SKILL.md` to spawn generators, runners, evaluators, fixers, and diagnosers through native
subagents.

Keep gateway mode temporarily available for comparison.

### Phase 4: Add convergence and artifact auditing

Implement state transitions, iteration tracking, failed-scenario reruns, and artifact auditing.
Interruption recovery may be added without changing the public artifact contract.

### Phase 5: Cross-harness conformance

Run the same scenarios unchanged in:

- Claude
- Cursor
- OpenCode

Verify role isolation, parallelism, JSON compliance, report parity, and safety boundaries.

### Phase 6: Retire gateway orchestration

Remove:

- PydanticAI model setup
- LLM Gateway credentials
- Gateway-specific model configuration
- LLM calls from `swarm_simulation.py`

Remove the gateway execution path after native-subagent parity is reached.

## Acceptance criteria

- No LLM Gateway credentials are needed. Credentials are never passed to subagents; M2 controlled
  executors may use scoped credentials.
- All reasoning occurs in fresh native subagents.
- Runner and evaluator are independent.
- Outputs conform to validated schemas.
- Confirmed scenarios remain authoritative.
- Errors never count as passes.
- Prompt patches are fully audited.
- Structural code changes require approval.
- The active harness model is used by default and recorded when the harness exposes it.
- The skill supports both standalone activation and post-coding Agent Assist handoff.
- The same skill works in Claude, Cursor, and OpenCode without harness-specific instructions.