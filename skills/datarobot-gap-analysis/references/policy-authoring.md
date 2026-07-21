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

severity_overrides:
  SEC-011: critical                 # bump/lower a specific condition's severity

posture:
  patch_max: 0.25                   # tune the Patch/Hybrid/Re-platform thresholds
  replatform_min: 0.50

scan:
  exclude: ["**/vendor/**"]         # extra paths to skip during inventory
  max_file_bytes: 200000            # per-file byte cap fed to Layer-2 prompts

report:
  fail_on: ["critical", "high"]      # non-zero exit code when any of these remain
```

## Adding a condition (no code change)

Append an entry to `scripts/taxonomy.yaml` following the existing shape (`id`, `pillar`,
`layer`, `severity`, `title`, `description`, `files_glob`, `detector`, `remediation`,
`fix_type`). For a Layer-2/4 (LLM-based) condition, also add a prompt file under
`scripts/prompts/` following the shape of `prompts/_contract.md` (detection) or
`prompts/_fix_contract.md` (fix). Point `GAP_DATA_DIR` at a directory containing your
extended `taxonomy.yaml` (plus `policy/` and `prompts/`) to run against it instead of
the vendored defaults — this is the supported mechanism for an org to fork the
taxonomy without forking the engine.

## Open question (not resolved by this skill)

What format an org submits its own standards in, and whether those checks should be
weighted above the baseline 40, is a product decision still open on the mini-PRD. The
policy-YAML mechanism above is the current answer; treat it as a reasonable default,
not a settled one.
