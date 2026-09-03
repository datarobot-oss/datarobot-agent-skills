# The Assessment Framework

The engine evaluates every submitted repository against a registry of 33 static
conditions, defined in `scripts/taxonomy.yaml`, plus a dynamic regulatory layer
whose checks come from the org's own DataRobot risk-management policy at run
time (see below). Each static condition belongs to exactly one pillar and is
evaluated by exactly one layer.

## Seven risk pillars

| Pillar | ID prefix | # conditions | What it evaluates |
|---|---|---|---|
| Security | `SEC` | 9 | Secret exposure, prompt-injection vectors, encryption, input validation |
| Identity | `IDN` | 4 | Human/shared identity, credential rotation, RBAC, over-permissioning |
| AI Governance | `AIG` | 8 | Guardrails, model pinning, approved models, evals, human-in-loop, cost controls, grounding, prompt versioning |
| Reliability | `REL` | 6 | Tests, CI, lint gates, lockfiles, retry logic, resilience, fallback paths |
| Ops | `OPS` | 3 | Structured logging, tracing, health checks |
| IT Conformance | `ITA` | 5 | Python version floor, library allow/deny, approved models, licenses, base images |
| Regulatory & Policy | `POL` | dynamic | Whatever mitigations the org's DataRobot risk-management policy requires (EU AI Act by default). Not defined in `taxonomy.yaml`; finding ids look like `POL-DR-<MITIGATION-TYPE>`. |

## Four evaluation layers

| Layer | Mechanism | # conditions | Degrades to |
|---|---|---|---|
| 1 - Deterministic | A built-in secret scanner, `trivy` (dependency CVEs, secrets, IaC misconfiguration, dependency licenses) with `pip-audit` and `npm audit` as the fallback, `gitleaks` for secrets in git history, `hadolint` for Dockerfiles, `semgrep`, plus presence checks: tests, CI, lint/type-check gate, lockfiles, dependency updates, vulnerability scanning, CODEOWNERS, action pinning | 15 | Optional scanners that aren't installed are skipped and named in the report. Layer 1 always runs. |
| 2 - LLM reasoning | A per-condition prompt template (under `scripts/prompts/`) reads the condition's `files_glob` and reasons about the code. Relational checks (`SEC-001`, `IDN-003`) require *both* file groups involved, or are marked skipped-with-reason, never guessed. | 20 | Skipped, with a stated reason, if no LLM client is configured. |
| 3 - Conformance | Compares the repo's declared Python version, dependencies/imports, model ids, licenses, and base images against the merged policy. | 6 | Runs fully offline; no LLM needed. |
| 4 - Regulatory | Fetches the org's DataRobot risk-management policy (named by `regulatory.policy_name`, default "EU AI Act"); for each required mitigation, the LLM judges whether the repo shows evidence it is implemented, or configured to be provided by DataRobot at deployment time. Unsatisfied mitigations become findings. Needs `DATAROBOT_API_TOKEN`/`DATAROBOT_ENDPOINT`. | dynamic | Skipped, with a stated reason, if DataRobot risk-management isn't reachable (no local fallback checklist). With `--no-llm`, required mitigations are reported as "required, not assessed" instead of judged. |

## Severity scale

Every finding carries one of: `critical`, `high`, `medium`, `low`. For Layers 1-3
severities are condition defaults in `taxonomy.yaml`; a policy file can override
them per-condition via `severity_overrides`. Layer 4 findings take their default
severity from `scripts/risk_management_mitigations.yaml` instead.

## Fix classification

Every condition also carries a `fix_type`, which drives what the remediation step
offers:

- **auto**: a deterministic codemod (secret → env var + `.gitignore` entry, model
  pin, dependency bump, Python version pin, CI/test/logging scaffold).
- **assisted**: an LLM-generated patch shown as a reviewable diff (narrowing a tool's
  scope, adding validation, adding retries, adding guardrails).
- **advisory**: written guidance only; no automated fix exists (these are also the
  findings most likely to be flagged `structural`, see
  [remediation-paths.md](remediation-paths.md)). Layer 4 findings are advisory by
  default: satisfying a risk-management mitigation almost always means adopting the
  corresponding DataRobot platform feature (deployment monitoring, GenAI Guards,
  RBAC, Model Registry documentation), not patching the repo in place. The
  exception: on a repo that already carries a pulumi-datarobot program, the
  mitigations enabled by IaC (deployment drift/accuracy/fairness settings,
  notification policies, guard configurations) become **assisted** fixes that
  propose the missing settings block into the existing Pulumi resources, and stop
  counting as structural.

## Extending the framework

To add a Layer-2 (LLM) check, append a condition to `scripts/taxonomy.yaml` and add
its prompt file under `scripts/prompts/`; no code change is needed. Layer-1 and
Layer-3 conditions also need a detector in `scripts/gap_analysis/scanners.py` or
`conformance.py`. This is also the mechanism for an org to layer its own
standards on top of the baseline: point `--policy` at a file that adds
`severity_overrides` or tightens `it_admin` values, and add any org-specific
conditions directly to a copy of `taxonomy.yaml` referenced via `GAP_DATA_DIR`.

Layer 4 is extended in DataRobot, not here: an admin edits the org's
risk-management policy (or authors a new one and points `regulatory.policy_name`
at it), and the next run picks it up automatically. The only skill-side asset is
`scripts/risk_management_mitigations.yaml`, remediation metadata per mitigation
*type*, which only needs a new entry when DataRobot itself introduces a new
mitigation type (run `scripts/validate_risk_management_mapping.py` to detect
that).
