# Proposal: Automated Behavioral Testing for DataRobot Agent Skills

**Status:** v0 + v1 implemented; v2 first-wave scenario coverage implemented (see amendments below)
**Author:** Matthew Hausknecht (drafted with Claude)
**Date:** 2026-08-17 (amended 2026-08-18, 2026-08-20)
**Related:** [datarobot-agent-skills](https://github.com/datarobot-oss/datarobot-agent-skills), [datarobot-agent-tester](https://github.com/datarobot-oss/datarobot-agent-tester)

---

## Amendments (2026-08-18, during v0/v1 implementation)

1. **Scenario location (§4.1 amended).** Scenarios live in `tests/behavioral/`
   (`journeys/` for multi-skill chains, `scenarios/<skill-name>/` for
   single-skill scenarios), **not** co-located under `skills/<name>/scenarios/`
   as originally proposed: everything under `skills/` ships to end users
   through every packaging channel (npm `files`, Claude/Cursor
   `skills_directory`, gemini extension), which would leak test internals to
   customers and let the agent under test read its own `success_checks`.
   CODEOWNERS entries on `tests/behavioral/` preserve co-review;
   `skills_under_test` in the YAML drives selection.
2. **v1 driver is OpenCode, not Claude Code (§4.2 amended).** Plain
   `opencode` CLI (pinned version) configured against the DataRobot LLM
   Gateway — reuses existing DataRobot credentials in CI instead of a separate
   Anthropic API provisioning path. Verified: `opencode run --format json`
   emits per-tool-call events with inputs/outputs/errors, tokens, and cost;
   skills load through OpenCode's built-in `skill` tool so **skill triggering
   is a first-class observable event**. Claude Code remains the natural second
   driver behind the same `AgentDriver` protocol.
3. **Sandbox (§4.2 refined).** v1 isolation is an isolated HOME/XDG tree plus
   a from-scratch env allowlist (verified: OpenCode fully honors the
   overrides, and headless mode auto-rejects file access outside the project
   directory). Hosted CI runners are already ephemeral VMs; a Docker layer for
   network-egress control is v2 hardening.
4. **Resource naming.** Run ids follow
   `drat-<context>-<condition>-r<n>-<timestamp><4hex>`; the `drat-` family
   prefix is what the sweeper (`dr-agent eval sweep`) matches, and the
   embedded timestamp is its age fallback.
5. **Engine surface.** Implemented in `datarobot-agent-tester` as
   `dr-agent eval run-behavioral` / `dr-agent eval sweep`, an
   `ExecutionBackend` seam (the original plan eval is `PlanBackend`,
   unchanged), scenario schema v2 (`kind: behavioral`), a success-check
   registry, trajectory normalization with capability-honest metrics, and a
   `[behavioral]` extra carrying the DataRobot SDK.

## Amendments (2026-08-20, during v2 first-wave implementation)

6. **Fixture-id injection (§4.1 extended).** Scenarios that assert against
   pre-provisioned resources declare `requires_env:
   [BEHAVIORAL_FIXTURE_...]` and reference the ids as `{env:VAR}` tokens in
   the prompt, `env` values, and string check params. Fail-loud at three
   layers: parse time (references must be declared; names must match
   `BEHAVIORAL_*`/`DRAT_*` so credentials can never be templated), run start
   (missing variables abort before any agent tokens are spent), and
   substitution. Long-lived fixtures are built by
   `tests/behavioral/fixtures/provision_fixtures.py` and named with the
   **`bfix-` prefix** — deliberately outside the `drat-` family so teardown
   and the sweeper can never delete them.
7. **Trace read API verified.** `GET
   api/v2/otel/experiment_container/<use_case_id>/traces/` returns trace
   summaries (traceId, spansCount, errorSpansCount, …); observed ingestion
   latency is under a minute. `dr_traces_received` therefore shipped with
   checks wave 1 instead of a follow-up PR, polling with a deadline.
8. **Expected-trigger metric (§4.3 extended).** The live feature-impact spike
   showed `datarobot-model-explainability` organically claiming "analyze the
   feature importance for my model" (and passing the outcome via SHAP) —
   the trigger collision §4.3's `skill_triggered` boolean cannot see. Runs
   now also record `skill_triggered_expected` (any triggered skill ∈
   `skills_under_test`) and reports aggregate an expected-skill trigger
   rate. Report-only, never gated.
9. **Multi-directory scenario discovery.** `--scenarios` is repeatable and
   each directory is scanned one subdirectory level deep, so
   `tests/behavioral/scenarios` picks up every `scenarios/<skill>/` dir in
   one invocation (one aggregated report); duplicate scenario ids across
   directories are rejected.

---

## 1. Problem & Motivation

### The manual testing burden

Every PR to `datarobot-agent-skills` is currently validated by hand: human developers
install the changed skill into one or more coding agents (Claude Code, Cursor, Codex,
Gemini CLI, …), prompt the agent through a representative user journey, and eyeball
whether the agent reached a good outcome. This is:

- **Slow** — a single train→deploy→predict journey takes tens of minutes per agent.
- **Expensive** — it consumes senior developer time on every PR, for every affected skill.
- **Inconsistent** — different testers use different prompts, agents, and success bars,
  so "it worked for me" is not comparable across PRs or over time.
- **Non-regressive** — a PR that improves one skill can silently break a linked journey
  (e.g., a deployment-skill change that breaks the predictions skill's assumptions), and
  nobody re-tests the unchanged skills.

### What automated testing exists today doesn't cover the gap

| Layer | What it checks | What it misses |
|---|---|---|
| `task lint` / `tests/integration/` | Naming, structure, frontmatter, Python lint | Anything about skill *content* |
| `tests/e2e/` (LLM judge via `dr_agents_tester`) | An LLM reads SKILL.md and critiques clarity/completeness | Whether an agent *following* the skill actually succeeds |

The e2e judge is static review: it catches confusing prose but cannot catch the failure
modes that actually burn users:

- **API drift** — the skill references an SDK method that was renamed/deprecated
  (this class of bug is why `datarobot-model-explainability` had to pin
  `datarobot>=3.6.0` and steer away from the legacy `ShapMatrix` path).
- **Trigger failure** — the skill's `description` frontmatter doesn't match how users
  phrase the task, so the agent never loads it and freelances.
- **Trajectory waste** — the agent eventually succeeds, but only after dead ends,
  hallucinated methods, and retries that a better-written skill would prevent.
- **Broken chains** — individually fine skills that hand off badly
  (train → deploy → predict).

### Why this matters strategically

These skills are customer-facing and distributed through multiple marketplaces
(Claude plugin marketplace, Cursor, Gemini extensions, the universal installer). A skill
that fails in a customer's IDE is a product defect, not a docs typo. Additionally, this
repo's own admission criteria (CLAUDE.md) ask of every skill: *"Is the task complex
enough? Can an LLM with basic tools achieve the same result?"* — a question we currently
cannot answer with data.

### What we want instead

A harness that, for any skill (or linked set of skills):

1. Spins up a sandboxed coding agent with the skills installed the same way users
   install them.
2. Prompts it through a defined user journey.
3. **Verifies the outcome programmatically** against real DataRobot state.
4. Scores the trajectory: time, tokens, turns, dead ends, whether the skill triggered.
5. Runs automatically when a PR touches the relevant skill, and compares
   PR-branch vs. main vs. no-skill-at-all.
6. Produces metrics stable enough that a future optimization loop can search over
   skill text to maximize outcomes.

---

## 2. Goals & Non-Goals

**Goals**

- Replace the bulk of manual PR testing with automated behavioral runs.
- Ground-truth outcome verification (DataRobot API state), not judge vibes.
- Quantified efficiency metrics per (skill, scenario, agent, condition).
- PR-scoped test selection: only re-run what a change can affect.
- Statistical honesty about nondeterminism (k trials, pass@k, significance tests).
- A metrics substrate that a later skill-optimization loop can consume.

**Non-Goals (for now)**

- Automated skill rewriting. The repo strongly prefers human-written skills; any
  optimization loop proposes diffs for human review (see §9).
- Testing every coding agent from day one. v1 is Claude Code headless; the driver
  interface keeps others cheap to add (§5.2).
- Replacing `task lint` or the static LLM judge — those stay as fast, cheap first lines.

---

## 3. Current State of `dr_agents_tester`

The natural home for this harness already exists. `dr_agents_tester` (hackathon-origin,
OSS) has two halves:

1. **Skill-text judge** (`skills.py`, `pytest_plugin.py`) — what `tests/e2e/` here uses
   today. Static SKILL.md critique with an MD5 hash cache (`HashCache`) so CI only pays
   for changed skills.
2. **Eval framework** (`eval/`) — a scenario-based A/B evaluation harness with exactly
   the right skeleton:
   - Scenario YAML (`prompt`, `expected_files`, `expected_approach`,
     `common_pitfalls`, `acceptance_criteria`, difficulty tiers) — `eval/scenarios.py`
   - **Conditions**: each scenario runs under `no_context` / `generated` / `refined`
     AGENTS.md variants — `eval/models.py: ConditionType`
   - **n runs per cell**, mean/std, and pairwise t-tests with p-values — `eval/stats.py`
   - Token and duration tracking per run; Markdown + JSON reports — `eval/report.py`

**The gap is one function.** `eval/runner.py:_run_single` implements the "agent" as a
single LLM call that writes an *implementation plan* against a static `repo_tree.txt`,
and a second LLM scores the plan. There is no tool use, no filesystem, no execution, and
no DataRobot backend. Everything upstream (scenarios, conditions) and downstream
(scoring, stats, reports) survives; the middle needs to become "drive a real coding
agent in a sandbox and assert real outcomes."

---

## 4. Proposed Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ CI trigger (PR label / nightly / manual)                         │
│   └─ changed-files → skill mapping → scenario selection          │
├──────────────────────────────────────────────────────────────────┤
│ Evaluator (exists: eval/runner.py)                               │
│   scenarios × conditions × k runs                                │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │ ExecutionBackend (NEW)                                     │ │
│   │   PlanBackend      — today's single-LLM-call plan eval     │ │
│   │   AgentBackend     — headless coding agent in sandbox      │ │
│   │   AgentLiveBackend — AgentBackend + real DataRobot org     │ │
│   │       ┌──────────────────────────────────────────────┐     │ │
│   │       │ AgentDriver (NEW)                            │     │ │
│   │       │   ClaudeCodeDriver (v1) │ CodexDriver │ …    │     │ │
│   │       └──────────────────────────────────────────────┘     │ │
│   └────────────────────────────────────────────────────────────┘ │
│   Outcome checks (NEW, programmatic, vs. DataRobot API)          │
│   Trajectory normalization (NEW) → metrics                       │
│   Trajectory judge (adapted from existing scoring prompts)       │
├──────────────────────────────────────────────────────────────────┤
│ Scoring / stats / reports (exists: scoring.py, stats.py,         │
│   report.py — extended with hard outcome fields)                 │
└──────────────────────────────────────────────────────────────────┘
```

### 4.1 Scenario schema v2

Scenarios live **in this repo**, co-located with the skill they test
(`skills/<name>/scenarios/*.yaml`), so CODEOWNERS covers skill + tests together.
`dr_agents_tester` stays the engine. New fields on top of the existing schema:

```yaml
scenarios:
  - id: train-deploy-predict-golden
    name: "Golden journey: train, deploy, predict"
    difficulty: medium
    skills_under_test:            # NEW — drives PR→scenario selection
      - datarobot-model-training
      - datarobot-model-deployment
      - datarobot-predictions
    prompt: |
      Train a model to predict churn using ./fixtures/churn_small.csv,
      deploy the best model, and score ./fixtures/churn_holdout.csv with it.
    fixtures:                     # NEW — files copied into the sandbox workspace
      - fixtures/churn_small.csv
      - fixtures/churn_holdout.csv
    env:                          # NEW — constraints injected into the run
      automl_mode: quick          # keep runs fast/cheap
      resource_prefix: "{run_id}" # all created DR resources must carry this
    success_checks:               # NEW — programmatic, authoritative
      - type: dr_project_exists
        name_contains: "{run_id}"
      - type: dr_deployment_healthy
        name_contains: "{run_id}"
      - type: dr_predictions_returned
        min_rows: 50
      - type: file_exists
        path: predictions.csv
    rubric: |                     # judge guidance for *process* quality only
      Penalize: legacy Project.start() API era, retries caused by hallucinated
      SDK methods, skipping the Use Case linkage the training skill mandates.
    common_pitfalls: [...]        # kept from v1 — feeds the rubric
    timeout_minutes: 25
```

**Design rule:** `success_checks` decide pass/fail; the LLM judge only scores *how* the
agent got there. Judges are unreliable on "did it work"; the DataRobot API is
authoritative. Check types are a small library of Python assertions
(`dr_project_exists`, `dr_deployment_healthy`, `dr_predictions_returned`,
`dr_traces_received` for the monitoring skill, `file_exists`/`file_matches` for local
outputs, …) — extended as new skills need them.

### 4.2 AgentDriver interface

```python
class AgentDriver(Protocol):
    name: str            # "claude-code", "codex", ...
    version: str         # pinned CLI version, recorded in results

    def run(
        self,
        workspace: Path,          # sandbox dir with fixtures + skills installed
        prompt: str,
        env: dict[str, str],      # scoped DR credentials, endpoint
        timeout: timedelta,
    ) -> RawTranscript: ...
```

**v1 = `ClaudeCodeDriver`** using `claude -p --output-format stream-json` inside a
Docker container. Rationale: its JSONL stream is the richest and most stable —
per-event tool calls with full inputs, tool results including errors, an init event
listing loaded skills, and a final result with `num_turns`, durations, token usage, and
cost. Two things fall out for free:

- **Exact skill-trigger detection** — skill activation is an observable transcript
  event, so "the skill never fired" (a `description` frontmatter bug) is a first-class,
  measurable failure mode.
- **Efficiency metrics without instrumentation** — turns, tool calls, error/retry
  counts, wasted work (edit-then-revert), tokens, wall time.

Codex (`codex exec --json`) is the natural second driver; Gemini CLI and cursor-agent
emit coarser output, so their adapters will mark some metrics unavailable rather than
fake them.

**Sandbox contract:** fresh container per run; pinned agent CLI version; skills
installed via the same installer users run (this also tests packaging); a scoped
DataRobot API token; the workspace pre-seeded with scenario fixtures; no network access
beyond the DataRobot endpoint and the agent's model API.

### 4.3 Normalized trajectory schema

Per-driver adapters convert raw transcripts into a common event stream the scoring layer
consumes, so scoring never knows which agent ran:

```
TrajectoryEvent = turn_start | tool_call{name, input_digest} | tool_result{ok, error}
                | skill_triggered{skill_name, turn} | tokens{in, out} | done{...}
```

Derived metrics per run: `outcome_pass` (from success_checks), `wall_seconds`,
`total_tokens`, `num_turns`, `num_tool_calls`, `num_errors`, `num_retries`,
`skill_triggered` (bool + turn), `judge_score` (soft, 0–1). Raw transcripts are archived
as CI artifacts — over time this becomes the dataset that powers regression triage and
any optimization work.

### 4.4 Conditions: measuring skill lift

Repoint the existing `ConditionType` mechanism from AGENTS.md variants to skill
variants:

| Condition | Question it answers |
|---|---|
| `no_skill` | Baseline — can the agent do this with just the SDK? Directly operationalizes CLAUDE.md's "is the task complex enough to be a skill?" criterion. |
| `skill_main` | Current released behavior. |
| `skill_pr` | The PR under review. |

A PR run is then a pairwise comparison the existing `stats.py` t-test machinery already
computes: *did `skill_pr` beat `skill_main`, and does either beat `no_skill`?*

### 4.5 Nondeterminism & gating

- k trials per cell: **k=3 on PR runs, k=5–10 nightly.**
- Report pass@k and mean efficiency with std; gate on **regression vs. the stored
  baseline** for (skill, scenario, agent), not absolute thresholds — this also catches
  drift when an agent CLI version bump changes behavior.
- Behavioral tests start **advisory** (comment on the PR, don't block merge) until
  observed flake rates justify making them required.

---

## 5. DataRobot Backend Strategy

Skills create real projects, deployments, and AutoML runs, so outcome checks need a real
backend. Three tiers:

| Tier | Backend | When | Cost/fidelity |
|---|---|---|---|
| Smoke | Lightweight fake DR API server (records calls, canned responses) | Every PR, fast | Cheap; validates call shapes only, drifts from real API |
| **Live (primary)** | **Dedicated test org on app.datarobot.com** | PR label + nightly | Real outcomes; Quick-mode AutoML on toy datasets keeps runs ~minutes |
| Pre-release | staging.datarobot.com | Optional, before releases | Highest internal fidelity |

**Why app.datarobot.com over staging as the CI backbone:** staging requires Global VPN,
which vanilla GitHub Actions runners cannot reach. The alternatives — self-hosted
runners inside the VPC — are a known security footgun on a *public* repo (fork PRs
executing on internal infrastructure), and an internal mirror pipeline adds coupling.
A dedicated prod test org is reachable from hosted runners, and is arguably the more
honest environment: it's what customers' agents actually hit. Staging becomes a
nice-to-have pre-release check run from inside the network, not the CI path.

**Hygiene requirements:**

- Fresh, scoped, org-isolated **service-account credentials** minted for this harness —
  never tokens copied from wiki pages (several internal Confluence pages are known to
  contain pasted live credentials; treat those as radioactive).
- Every created resource carries a `{run_id}` prefix; a teardown job deletes by prefix
  after each run, plus a nightly sweeper for leaked resources older than 24h.
- Quota/budget alarms on the test org.

**Record/replay (VCR cassettes) considered and rejected** as the primary strategy:
agents don't make deterministic call sequences, so cassette misses would dominate.

---

## 6. CI Integration

- **Changed-files → skills mapping:** the `skills/<name>/` layout makes this a path
  prefix match; the existing `HashCache` pattern already proves the approach.
- **Dependency manifest** (`tests/e2e/skill_deps.yaml` or similar): predictions depends
  on deployment depends on training; agent-assist sub-skills link. A change to a skill
  re-runs its own scenarios **plus chained journeys that pass through it**.
- Changes to shared infra (CLAUDE.md, plugin configs, installer paths) trigger a sampled
  subset, not the full matrix.
- **Triggers:** fake-server smoke on every PR; live runs on a `run-e2e` PR label
  (maintainer-applied — this also protects the test-org credentials from fork PRs, since
  labels require maintainer action); full matrix nightly.
- **Output:** a PR comment table — per scenario: pass@k, Δ vs. main, Δ vs. no-skill,
  efficiency deltas, links to transcript artifacts.

---

## 7. Relationship to `dr_agents_tester`

Proposed as an extension, pending the original author's input. Concrete extension
points:

| Change | Where | Nature |
|---|---|---|
| `ExecutionBackend` protocol; `_run_single` delegates to it | `eval/runner.py` | The core surgery — today's LLM call becomes `PlanBackend` |
| `AgentDriver` + `ClaudeCodeDriver` + sandbox management | new `eval/drivers/` | New code |
| Scenario schema v2 fields (`skills_under_test`, `fixtures`, `success_checks`, `env`) | `eval/scenarios.py`, `eval/models.py` | Additive |
| Skill-variant `ConditionType` (`no_skill`/`skill_main`/`skill_pr`) | `eval/models.py` | Additive |
| Outcome-check library (DR API assertions) | new `eval/checks/` | New code |
| Trajectory normalization + metrics | new `eval/trajectory.py` | New code |
| `ScoreCard` gains hard fields (`outcome_pass`, efficiency metrics) | `eval/models.py`, `eval/scoring.py` | Additive; gate moves to hard fields |
| Reports gain pass@k + baseline-delta sections | `eval/report.py`, `eval/stats.py` | Additive |

Scenario YAML, fixtures, and the dependency manifest live in **datarobot-agent-skills**;
the engine, drivers, and check library live in **datarobot-agent-tester**. If the
original author prefers to keep the package scoped to AGENTS.md work, the fallback is a
sibling package that depends on it and reuses `eval/stats.py` + `eval/report.py`.

---

## 8. Phasing

| Phase | Deliverable | Exit criterion | Status (2026-08-20) |
|---|---|---|---|
| **v0** | `ExecutionBackend` refactor in dr_agents_tester; `PlanBackend` preserves current behavior; scenario schema v2 parser | Existing evals green under new interface | ✅ Done — [tester PR #10](https://github.com/datarobot-oss/datarobot-agent-tester/pull/10) |
| **v1** | Agent driver (OpenCode, per amendment 2) + sandbox; one golden journey (upload→train(Quick)→deploy→predict) with `success_checks`; k configurable; transcript artifacts; nightly + `run-e2e` label workflow (inert) | Golden journey runs unattended end-to-end | ✅ Done — golden journey **passed live** (all 4 checks, 21.5 min, all 3 skills triggered, zero leaked resources); `no_skill` baseline condition also landed early. CI workflow merged inert, pending the test org |
| **v2** | Scenario coverage for remaining skills; dependency manifest + PR-scoped selection; PR comment reports | Most PRs need no manual testing | ◐ First wave done — all five README journeys live-verified 6/6 in one aggregated run (amendments 6–9); selection + PR comments remain. See §10a |
| **v3** | Trajectory judge; second driver (Claude Code); baseline-regression gating | Behavioral checks become required (if flake rate allows) | ⬜ See §10a roadmap |
| **v4** | Optimization advisor (§9) | First judge-guided skill improvement merged via human review | ⬜ Distant aspiration |

v1 alone removes most of the manual burden for the most-exercised path.

---

## 9. Future: Skill Optimization Loop

With scalar rewards per (skill, scenario) — pass@k, efficiency, trigger rate — a
textual-optimization loop (GEPA/OPRO-style) is mechanically straightforward: failing
trajectories → judge critique → proposer edits SKILL.md → re-eval → keep if better. Two
governing constraints:

1. **Advisor, not auto-committer.** This repo explicitly prefers human-written skills.
   The loop emits proposed diffs *with evidence* ("this edit raised pass rate 60%→90%
   over 10 trials; transcripts attached") as draft PRs for human review.
2. **Held-out scenarios.** Skill text optimized against 3 scenarios will Goodhart them.
   Maintain a held-out scenario set the optimizer never sees, and rotate it.

Nothing in v1–v3 needs to change to enable this; the transcript archive and metrics
schema are designed so the optimizer is purely additive.

---

## 10. Risks & Open Questions

| Risk / question | Notes |
|---|---|
| Live-run cost & duration | Quick-mode AutoML + toy datasets targets <15 min/scenario; budget alarms on the test org. Needs a measured baseline in v1. |
| Flakiness blocking merges | Start advisory; promote to required per-scenario once flake rate <~5% at k=3. |
| Test-org provisioning & ownership | Who owns the org, quota, and the service account? Needs an owner before v1. |
| Fork-PR credential safety | Live runs only via maintainer-applied label; secrets never exposed to fork workflows. |
| Agent CLI version drift | Pin versions in the sandbox image; version recorded per result; nightly canary against `latest`. |
| `dr_agents_tester` stewardship | Original author's appetite for this extension — this doc is the conversation starter. Fallback: sibling package (§7). |
| Judge model choice | Existing cross-model pattern (generator ≠ judge) should carry over to trajectory judging. |
| Scenario authoring cost | Each skill needs 2–3 scenarios + checks. Mitigation: check-type library keeps YAML small; scenario authoring becomes part of the skill-contribution checklist in CONTRIBUTING.md. |

---

## 10a. Roadmap: remaining work (updated 2026-08-19)

**This section is the single source of truth for what is left to build.** v0 and
v1 are implemented and live-verified ([tester PR #10](https://github.com/datarobot-oss/datarobot-agent-tester/pull/10),
[skills PR #87](https://github.com/datarobot-oss/datarobot-agent-skills/pull/87));
usage documentation lives in the engine's
[docs/behavioral-evaluation.md](https://github.com/datarobot-oss/datarobot-agent-tester/blob/main/docs/behavioral-evaluation.md).
Items are ordered roughly by dependency, not size.

### R. Rollout (operational, not features)

- **R1 — Merge the two PRs** (engine first; the skills-repo parse test and
  `task test:behavioral` depend on it).
- **R2 — Cut the engine's first release tag** (v0.2.0). Also settles the
  `datarobot/` vs `datarobot-oss/` URL drift; tighten the skills repo's
  `behavioral` (and `e2e`) uv-group pins from `@main` to the tag, then to a
  PyPI `==` pin once published.
- **R3 — Dedicated test org** (the only externally blocked step): org +
  scoped service-account token + budget/quota alarms + a named owner. Then:
  create the `behavioral-live` GitHub environment with
  `BEHAVIORAL_DATAROBOT_API_TOKEN`/`BEHAVIORAL_DATAROBOT_ENDPOINT`, run
  `provision_fixtures.py` against the test org and set the printed
  `BEHAVIORAL_FIXTURE_{PROJECT,MODEL,DEPLOYMENT}_ID` values as environment
  **variables** (ids aren't secrets; fixture-dependent scenarios stay out of
  CI until they exist), flip `vars.BEHAVIORAL_LIVE_ENABLED`, one supervised
  `workflow_dispatch` run, announce the `run-e2e` label. Until R3, the
  fixtures live in a developer account (bootstrapped 2026-08-20).
- **R4 — Accumulate the nightly baseline** (flake rate + cost per scenario;
  the <5%-at-k=3 bar from §4.5 decides when checks can become required).

### v2 — Coverage, selection, reporting

- **Scenario coverage for remaining skills** — ✅ first wave done
  (2026-08-20): all five README user journeys have live-verified
  single-skill scenarios under `tests/behavioral/scenarios/<skill>/`
  (training-start-automl, predictions-template, feature-impact-report,
  monitoring-drift-report, external-agent-otel). The check types this
  demanded all landed in the engine: `dr_use_case_exists`, `file_matches`,
  `dr_traces_received` (read side verified:
  `GET otel/experiment_container/<use_case_id>/traces/`), plus
  `dr_project_exists` stage/deadline params so "autopilot started" is
  checkable without waiting for AutoML. The fast every-PR predictions
  scenario exists via **pre-provisioned `bfix-` fixture resources**
  (`tests/behavioral/fixtures/provision_fixtures.py`) injected through the
  engine's `requires_env`/`{env:VAR}` mechanism; the engine also gained a
  `skill_triggered_expected` metric after the feature-impact spike showed
  `datarobot-model-explainability` organically claiming the journey.
  Remaining: 2–3 scenarios per skill (each skill has 1), Appendix A items
  4 (setup & recovery) and 5 (SHAP explainability), and scenarios for the
  skills outside the README's five journeys.
- **Dependency manifest + PR-scoped selection**: changed-files → skills
  mapping (path prefix), `skill_deps.yaml` for chained journeys, and
  scenario-edit → "run that scenario". Until this lands, every labeled run
  executes all journeys — acceptable at current scenario count, the reason
  scenario additions are CODEOWNERS-gated.
- **PR comment reports** (v1 is job-summary only): per-scenario pass@k,
  Δ vs. main, Δ vs. no-skill, efficiency deltas, artifact links.
- **Sandbox hardening**: `DockerSandbox` (network-egress allowlist) and the
  CI-parity image with a pre-warmed OpenCode home — build only if the
  cold-start stall seen once in the spikes recurs on runners.
- **Parallel throughput**: `opencode serve` + `--attach` per-run sessions if
  sequential k=3 cells become the wall-clock bottleneck.
- **Packaging-fidelity condition** (spike S8): install skills via the real
  npm plugin (`"plugin": ["file:<repo>"]`) instead of the byte-identical
  copy, as an occasional packaging test.

### v3 — Judging, gating, second driver

- **Trajectory judge**: rubric-driven soft scoring of *process* quality
  (`rubric` + `common_pitfalls` are already parsed, stored, and waiting);
  cross-model generator ≠ judge; extends `ScoreCard` — the six
  hardcoded-dimension sites in the engine are the known blast radius.
- **Second driver — Claude Code** (`claude -p --output-format stream-json`)
  behind the existing `AgentDriver` protocol; needs an Anthropic API
  credential path for CI, which is why OpenCode went first.
- **Baseline-regression gating**: store per-(skill, scenario, driver)
  baselines (nightly artifacts or a committed baselines file), gate on
  regression vs. baseline rather than absolute thresholds, promote scenarios
  to required as their flake rate clears the bar. Includes an agent-version
  canary (nightly `latest` vs. pin).
- **Cost accounting**: the LLM Gateway reports `cost: 0` in OpenCode's
  stream — derive $ from token counts + a price table so nightly cost
  tracking is real.

### v4 — Optimization advisor (§9; unchanged, distant)

Failing trajectories → judge critique → proposed SKILL.md diffs as draft PRs
with evidence; held-out scenario rotation. Everything it needs (per-run JSON,
transcripts, pass@k / trigger-rate metrics) is already being archived.

### Known loose ends (small, unscheduled)

- Nested sub-skill trigger naming: `skills_used` records whatever name the
  `skill` tool reports — verify agent-assist sub-skills surface distinctly
  (locks the trajectory-schema contract from amendment note; spike-level).
  Data point (2026-08-20): across six live runs, reported names always
  matched top-level skill directory names (including a chained
  `datarobot-data-preparation` sub-use); agent-assist sub-skills remain
  unexercised.
- `dr_predictions_returned --verify_server` is best-effort corroboration
  only; revisit if workspace-CSV assertions ever prove spoofable.
- Spike S7 leftovers: fresh-deployment `service_health` semantics are
  handled permissively (`unknown` passes); deployment deletion needed no
  deactivation in the live run — formalize both once the test org exists.
- `dr-agent eval report` regenerates behavioral markdown from saved JSON;
  a small trajectory-diff helper (compare two runs' tool-call sequences)
  would speed manual triage.

---

## Appendix A: Candidate golden journeys (v1–v2)

1. ✅ **Train→deploy→predict chain** (`datarobot-model-training`,
   `datarobot-model-deployment`, `datarobot-predictions`) — the highest-traffic path;
   checks: project exists, deployment healthy, predictions returned.
   (`journeys/train-deploy-predict.yaml`, v1)
2. ✅ **Predictions against a fixture deployment** (`datarobot-predictions` alone) — a
   pre-provisioned long-lived deployment in the test org removes AutoML from the loop;
   fast enough for every-PR live runs.
   (`scenarios/datarobot-predictions/prediction-template.yaml`, ~2 min live)
3. ✅ **External agent monitoring** (`datarobot-external-agent-monitoring`) — instrument a
   toy LangGraph agent in the sandbox; check: OTel traces arrive under the Use Case
   (`dr_traces_received`).
   (`scenarios/datarobot-external-agent-monitoring/instrument-toy-agent.yaml`)
4. ⬜ **Setup & recovery** (`datarobot-setup`) — sandbox with deliberately missing/invalid
   credentials; check: SDK client authenticates by the end. Exercises the
   auto-invocation contract in CLAUDE.md.
5. ⬜ **SHAP explainability** (`datarobot-model-explainability`) — checks the modern
   `datarobot.insights` API path is used (trajectory rubric) and a SHAP matrix is
   computed (outcome check); this is the skill where API drift already bit once.
   Note: a live run showed this skill *organically* triggering on plain
   "analyze the feature importance" phrasing (amendment 8), so its scenario
   should also pin down the description boundary with
   `datarobot-feature-engineering`.

The 2026-08-20 first wave additionally covered three journeys beyond this
list, straight from the README's published examples: training-start-automl
(start Quick AutoML without waiting — `dr_project_exists` with
`stage: modeling`), feature-impact-report, and monitoring-drift-report (both
against the pre-provisioned fixtures).
