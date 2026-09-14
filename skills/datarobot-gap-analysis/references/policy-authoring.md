# Policy Authoring

IT-admin and regulatory rules are data, not code. `scripts/policy/defaults.yaml` ships
opinionated, sensible defaults; a user or org supplies their own policy file (via
`--policy <path>`) which is **deep-merged** over those defaults:

- Scalars are overridden.
- Dicts merge recursively.
- Lists are **replaced**, not concatenated, unless the key ends in `_add` (e.g.
  `libraries.deny_add: ["telnetlib"]` appends to the default deny list instead of
  replacing it).
- Missing keys fall back to the defaults.

## What a policy file controls

```yaml
it_admin:
  python:
    min_version: "3.12"          # ITA-001
  libraries:
    allow: []                     # empty = allow-all; non-empty = strict allowlist
    deny: ["pycrypto"]             # always enforced
  models:
    allow: ["anthropic/claude-*", "datarobot/*"]   # glob patterns, ITA-003 / AIG-003
  licenses:
    deny: ["GPL-3.0", "AGPL-3.0"]  # SPDX ids, ITA-004
  base_images:
    allow: ["python:3.12*", "datarobot/*"]  # ITA-005

regulatory:
  packs: ["eu_ai_act"]             # which Layer-4 packs to run
  policy_name: "EU AI Act"          # policy name or id; on a name collision the org's own policy wins over the built-in

severity_overrides:
  SEC-011: critical                 # bump/lower a specific condition's severity (Layers 1-3)

posture:
  patch_max: 0.25                   # tune the Patch/Hybrid/Re-platform thresholds
  replatform_min: 0.50

scan:
  exclude: ["**/vendor/**"]         # extra paths to skip during inventory
  max_file_bytes: 200000            # per-file byte cap fed to Layer-2 prompts

report:
  fail_on: ["critical", "high"]      # non-zero exit code when any of these remain
```

## Adding a condition

Append an entry to `scripts/taxonomy.yaml` following the existing shape (`id`, `pillar`,
`layer`, `severity`, `title`, `description`, `files_glob`, `detector`, `remediation`,
`fix_type`). For a Layer-2 (LLM-based) condition, also add a prompt file under
`scripts/prompts/` following the shape of `prompts/_contract.md` (detection) or
`prompts/_fix_contract.md` (fix). Point `GAP_DATA_DIR` at a directory containing your
extended `taxonomy.yaml` (plus `policy/` and `prompts/`) to run against it instead of
the vendored defaults; this is the supported mechanism for an org to fork the
taxonomy without forking the engine.

Layer-2 conditions need no code change. Layer-1 and Layer-3 conditions also need a
detector in `scripts/gap_analysis/scanners.py` or `conformance.py`. Layer 4
(regulatory) has no taxonomy entries to add; it is extended by editing the org's
risk-management policy in DataRobot, see below.

## Layer 4: DataRobot risk-management, not a local checklist

There is no gap-analysis-defined regulatory checklist. When the `eu_ai_act` pack
is enabled (the default), Layer 4 fetches the org's DataRobot risk-management
policy (named by `regulatory.policy_name`, default `"EU AI Act"`) and assesses
the repo against every mitigation that policy requires. The org's admins own the
checklist by owning the policy in DataRobot; changing what Layer 4 checks means
editing the policy there, not a file here.

This is a pre-deployment, "would this be compliant if we deployed it" check. It
never inspects deployed entities; the policy's full mitigation list (union
across every risk tier) is used, the strictest honest reading for a repo that
isn't deployed anywhere yet.

Requirements and behavior:

- Needs `DATAROBOT_API_TOKEN`/`DATAROBOT_ENDPOINT` and an org with the
  risk-management feature enabled (not yet GA as of this writing; expect this to
  be unavailable in most orgs today). If it isn't reachable, Layer 4 reports
  nothing and says why in Engine Notes. There is deliberately no local fallback
  checklist, an empty section rather than misleadingly generic reassurance.
- Each required mitigation is judged by the LLM the same way Layer 2 judges its
  conditions: it reads the mitigation's relevant files (per-type `files_glob` in
  `risk_management_mitigations.yaml`) and decides whether there is evidence the
  mitigation is implemented in the repo, or configured to be provided by
  DataRobot at deployment time. Evidence found means no finding; no evidence
  means a confirmed gap.
- With `--no-llm` (or no LLM client), required mitigations are still fetched and
  surfaced, but as "required, not assessed" findings rather than confirmed gaps,
  never silently passed.
- Purely organizational requirements (staff AI literacy) are not assessable from
  code and always surface as "required, not assessed."

Remediation for these findings is almost always "adopt the DataRobot platform
feature that provides this" (deployment monitoring, GenAI Guards, RBAC, Model
Registry documentation), not a code patch, which is why they are all advisory
and almost all structural: complying with the org's policy generally means
converting the architecture to deploy through DataRobot, the natural fit for the
Re-platform path in [remediation-paths.md](remediation-paths.md).

The only skill-side asset is `scripts/risk_management_mitigations.yaml`:
assessment and remediation metadata (title, default severity, what counts as
evidence, which files to inspect, which DataRobot feature satisfies it) per
mitigation *type*, DataRobot's stable enum, never section names, which are
admin-editable free text. It needs a new entry only when DataRobot itself
introduces a new mitigation type. Run
`scripts/validate_risk_management_mapping.py` periodically against a live org to
detect that drift; a required type with no metadata entry still surfaces in the
report as "unrecognized mitigation type" rather than being silently dropped.

Known limitation: policies are looked up by name, and if an org has several
policies sharing one name, the first match wins. Prefer uniquely-named policies
until lookup by id is added.

### Remediation metadata per mitigation

Each entry in `scripts/risk_management_mitigations.yaml` carries, besides what to
assess, how to close the gap: `steps` (an ordered list the report renders under
**How**), `docs_url` (the DataRobot documentation page for the feature), and
`fix.via` / `fix.requires` (`pulumi` on a `deployment` or `custom_model`, `api`,
`automatic`, or `organizational`). The report's **Path to Compliance** section
groups the unsatisfied mitigations by what unblocks them: first the architectural
step when the Pulumi program has no `datarobot.Deployment` or `CustomModel` to
attach settings to, then Pulumi settings, then compliance tests in the LLM test
suite, then console or API work.

## Open question (not resolved by this skill)

What format an org submits its own non-regulatory standards in, and whether those
checks should be weighted above the baseline taxonomy, is a product decision
still open on the mini-PRD. The policy-YAML mechanism above is the current
answer; treat it as a reasonable default, not a settled one. (For regulatory
standards specifically, the answer is now: author them as a DataRobot
risk-management policy.)
