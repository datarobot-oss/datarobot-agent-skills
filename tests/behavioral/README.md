# Behavioral scenarios

Behavioral tests drive a **real coding agent** (OpenCode, pinned version)
through a realistic user journey with this repo's skills installed the same
way users install them, then verify the outcome **programmatically** against
real DataRobot state. They complement the static LLM judge in `tests/e2e/`
(which reviews skill *text*) by testing skill *behavior*: API drift, trigger
failures, trajectory waste, and broken skill chains.

The engine lives in
[datarobot-agent-tester](https://github.com/datarobot-oss/datarobot-agent-tester)
(`dr-agent eval run-behavioral`); this directory holds the scenarios and
fixtures. Design doc: [docs/proposals/skill-behavioral-testing.md](../../docs/proposals/skill-behavioral-testing.md).

## Layout

```
tests/behavioral/
  journeys/            # multi-skill user journeys (2+ skills_under_test)
  scenarios/<skill>/   # single-skill scenarios, one directory per skill name
  fixtures/            # committed CSVs + the seeded generator that made them
```

Scenarios live here — **never under `skills/`** — because everything in
`skills/` ships to end users through every packaging channel, and the agent
under test must not be able to read its own `success_checks`.

## Scenario schema (`kind: behavioral`)

```yaml
scenarios:
  - id: my-scenario                 # unique, kebab-case
    kind: behavioral                # required — plan-eval scenarios omit it
    name: "Human-readable name"
    difficulty: easy|medium|hard|expert
    prompt: |                       # what a real user would type — keep it natural;
      ...                           # {run_id} is substituted per run
    skills_under_test:              # drives (future) PR-scoped selection
      - datarobot-model-training
    fixtures:                       # copied into the sandbox workspace
      - source: ../fixtures/churn_train.csv   # relative to this YAML's directory
        dest: data/churn_train.csv            # path inside the workspace
    env:                            # injected into the agent's environment
      resource_prefix: "{run_id}"   # ALSO appends a prompt epilogue telling the
                                    # agent to prefix every DataRobot resource name
    success_checks:                 # programmatic, authoritative pass/fail
      - type: dr_project_exists
        name_contains: "{run_id}"
    rubric: |                       # guidance for the (future) trajectory judge —
      ...                           # process quality only, never pass/fail
    common_pitfalls: [...]
    timeout_minutes: 30
```

### Check types

| Type | Params | Asserts |
|---|---|---|
| `file_exists` | `path` (workspace-relative, glob ok), `min_bytes` | a file the agent was asked to produce exists |
| `dr_project_exists` | `name_contains` | a DataRobot project matching the run prefix exists |
| `dr_deployment_healthy` | `name_contains` | a matching deployment exists, has a model, isn't `failing` |
| `dr_predictions_returned` | `path`, `min_rows`, `prediction_column`, `verify_server` | a predictions CSV with enough rows and a prediction column |

New check types are added in the engine
(`dr_agents_tester/eval/checks/`) — keep scenario YAML small.

## Running locally

Behavioral runs create **real, run-prefixed resources in your DataRobot
account** and tear them down afterwards. You need `DATAROBOT_API_TOKEN` /
`DATAROBOT_ENDPOINT` (a `.env` works) and the pinned OpenCode version
(`npm install -g opencode-ai@<pinned>` — the run tells you the pin on mismatch).

```bash
task test:behavioral            # golden journey, your working-tree skills, k=1
task test:behavioral:baseline   # same scenario with NO skills installed
task test:behavioral:clean      # delete any leaked drat-* resources now
```

Per-run artifacts (raw transcript, normalized trajectory, check evidence)
land in `.behavioral-runs/<run_id>/`.

## Authoring guidelines

- **Prompts stay realistic.** Write what a user would actually type; never
  mention run ids or naming rules — `env.resource_prefix` injects that.
- **Checks decide pass/fail; the rubric never does.** If you can't assert it
  against the DataRobot API or the workspace, it belongs in `rubric`.
- Fixture data: commit small CSVs (DataRobot needs ≥20 rows to create a
  project; stay near a few hundred rows so Quick-mode AutoML stays fast) and
  regenerate them only via `fixtures/generate_fixtures.py` (seeded).
  `.gitignore` blanket-ignores `*.csv` — new fixture files need a negation
  entry (`!tests/behavioral/fixtures/*.csv` already covers this directory).
- One skill → `scenarios/<skill-name>/`; a chain of skills → `journeys/`.
- Scenario-only changes don't ship in any plugin package: **no plugin version
  bump, no CHANGELOG entry.**
