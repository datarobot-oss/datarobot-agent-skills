# The 40-Factor Framework

The engine evaluates every submitted repository against a fixed registry of 40
conditions, defined in `scripts/taxonomy.yaml`. Each condition belongs to exactly one
pillar and is evaluated by exactly one layer.

## Seven risk pillars

| Pillar | ID prefix | # conditions | What it evaluates |
|---|---|---|---|
| Security | `SEC` | 9 | Secret exposure, prompt-injection vectors, encryption, input validation |
| Identity | `IDN` | 4 | Human/shared identity, credential rotation, RBAC, over-permissioning |
| AI Governance | `AIG` | 8 | Guardrails, model pinning, approved models, evals, human-in-loop, cost controls, grounding, prompt versioning |
| Reliability | `REL` | 4 | Retry logic, resilience, fallback paths |
| Ops | `OPS` | 3 | Structured logging, tracing, health checks |
| IT Conformance | `ITA` | 5 | Python version floor, library allow/deny, approved models, licenses, base images |
| Regulatory & Policy | `POL` | 7 | EU AI Act control mapping (risk classification, transparency, technical documentation, record-keeping, human oversight, accuracy/robustness/security, prohibited-practice screen) |

## Four evaluation layers

| Layer | Mechanism | # conditions | Degrades to |
|---|---|---|---|
| 1 — Deterministic | `detect-secrets`, `pip-audit`, `semgrep`, plus presence checks (tests, CI) | 7 | A built-in regex secret scanner and dependency parser if those scanners aren't installed. Layer 1 always runs. |
| 2 — LLM reasoning | A per-condition prompt template (under `scripts/prompts/`) reads the condition's `files_glob` and reasons about the code. Relational checks (`SEC-001`, `SEC-006`, `IDN-003`) require *both* file groups involved, or are marked skipped-with-reason — never guessed. | 20 | Skipped, with a stated reason, if no LLM client is configured. |
| 3 — Conformance | Compares the repo's declared Python version, dependencies/imports, model ids, licenses, and base images against the merged policy. | 6 | Runs fully offline; no LLM needed. |
| 4 — Regulatory | Runs the enabled regulatory packs (EU AI Act today) as evidence-based control mapping, each finding citing the file/section it's grounded in. | 7 | Skipped, with a stated reason, if no LLM client is configured. |

## Severity scale

Every finding carries one of: `critical`, `high`, `medium`, `low`. Severities are
condition defaults in `taxonomy.yaml`; a policy file can override them per-condition
via `severity_overrides`.

## Fix classification

Every condition also carries a `fix_type`, which drives what the remediation step
offers:

- **auto** — a deterministic codemod (secret → env var + `.gitignore` entry, model
  pin, dependency bump, Python version pin, CI/test/logging scaffold).
- **assisted** — an LLM-generated patch shown as a reviewable diff (narrowing a tool's
  scope, adding validation, adding retries, adding guardrails).
- **advisory** — architectural findings get written guidance only; no automated fix
  exists (these are also the findings most likely to be flagged `structural`, see
  [remediation-paths.md](remediation-paths.md)).

## Extending the framework

No code change is needed to add a check: append a condition to `scripts/taxonomy.yaml`,
and for an LLM-based (Layer 2/4) check, add a prompt file under `scripts/prompts/`. This
is also the mechanism for an org to layer its own standards on top of the baseline 40 —
point `--policy` at a file that adds `severity_overrides` or tightens `it_admin` values,
and add any org-specific conditions directly to a copy of `taxonomy.yaml` referenced via
`GAP_DATA_DIR`.
