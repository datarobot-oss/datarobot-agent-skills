---
name: datarobot-gap-analysis
description: >-
  Use when the user wants to assess whether an AI agent repository (DataRobot-built
  or not) is enterprise-ready, run a gap analysis / readiness scan against security,
  governance, reliability, or regulatory standards, score an agent against EU AI Act
  requirements, or find and fix gaps (secrets, unpinned models, missing CI, missing
  guardrails, over-permissioned identity, etc.) before deploying an agent to
  production. Works on any repository, not only ones built with DataRobot.
---

# DataRobot Gap Analysis

This skill scores any agent repository (GitHub URL or local path) against an
**enterprise-readiness framework** spanning **seven risk pillars** (Security, Identity,
AI Governance, Reliability, Ops, IT Conformance, Regulatory & Policy) across **four
evaluation layers**: deterministic scanning, LLM-based code reasoning, policy
conformance, and a regulatory layer driven by the org's own **DataRobot
risk-management policy** (EU AI Act by default), not a hardcoded checklist. It then
recommends a remediation path (**Patch**, **Hybrid**, or **Re-platform**) and can
apply the safe fixes itself. Regulatory gaps are satisfied by adopting the DataRobot
platform feature the policy calls for (deployment monitoring, GenAI Guards, RBAC,
Model Registry documentation), so their remediation usually points at converting the
architecture to deploy through DataRobot rather than patching code.

Unlike `datarobot-agent-assist`, this skill needs nothing but a repo. It does not
require an `agent_spec.md` or a prior design conversation, so it works equally well on
an agent someone built entirely outside DataRobot.

---

## Prerequisite check

Run in order before proceeding:

1. **Git** — run `git --version`. If missing, tell the user to install it and stop.
2. **Python** — run `python3 --version`. If missing or below 3.11, tell the user to
   install Python 3.11+ and stop.
3. **uv** — run `uv --version`. If missing, tell the user to install it from
   https://docs.astral.sh/uv/getting-started/installation/ and stop. All script
   invocations below use `uv run`, which resolves the script's own dependencies
   (PyYAML) automatically, so there is no manual `pip install` step. The launcher
   locates the shared `datarobot-skills-utils` package itself: a repo checkout, an
   installed copy, or a one-time install from PyPI.
4. **Optional scanners**: check `which trivy gitleaks hadolint`. Any that is installed
   is used; without `trivy` dependency CVEs still come from `pip-audit`/`npm audit`,
   and without the others git-history secrets, IaC misconfiguration, dependency
   licenses and Dockerfile lint are skipped and named in the report. When one is
   missing, tell the user which checks will be skipped and offer to install it with
   the package manager native to their OS (Homebrew, apt/dnf, winget/scoop) or the
   release binary from the tool's own install docs. Install only if they agree; never
   install silently.
5. **DataRobot CLI**: run `dr --version`. If missing, invoke the
   `datarobot-setup` skill to install it, then re-check. The LLM layers (2 and 4)
   run through `dr opencode` workers authenticated by `dr auth`; without `dr` the
   engine falls back to direct API calls via litellm (add `--with litellm` to the
   `uv run` command in that case).

## Script path resolution

Resolve `<skill_scripts_dir>` once for the session: the `scripts/` subdirectory of the
directory containing this `SKILL.md`. Confirm it exists with
`ls <path_to_this_skill_dir>/scripts/`. Use the resolved absolute path for every
`<skill_scripts_dir>/...` reference below.

---

## Conversation flow

### 1. Collect the target

Ask for:
- **Repo**: a GitHub URL or a local path. Private GitHub repos need `GITHUB_TOKEN` in
  the environment — if cloning fails with an auth error, ask for a token or suggest the
  user runs `git clone` themselves and passes the local path instead.
- **Ref** (optional): branch/tag/commit to check out.
- **Policy** (optional): a path to an org policy YAML (Python version floor, approved
  models, license denylist, base images, EU AI Act pack toggles). If the user doesn't
  have one, run with the built-in defaults and mention that a custom policy is
  supported — see [references/policy-authoring.md](references/policy-authoring.md).
### 2. Check for DataRobot credentials, run the assessment

The LLM checks — the 20 Layer-2 code-reasoning conditions and Layer-4's
per-mitigation judging — run in parallel (default 4 workers, `--workers N`) through
a private `dr opencode` server the engine starts and stops automatically,
authenticated by the CLI's own login. `GAP_LLM_MODEL` overrides the model.
Layer 4's policy fetch from DataRobot risk-management uses
`DATAROBOT_API_TOKEN` + `DATAROBOT_ENDPOINT` when set, falling back to the dr
CLI's own config (written by `dr auth login`), so a logged-in machine needs no
env exports; `--env-file <path>` loads a project dotenv explicitly.
**If credentials are missing or invalid, invoke the `datarobot-setup` skill before
retrying**, do not print manual setup instructions. If the user explicitly wants a
fast pass, offer `--no-llm`: Layers 1 and 3 still run, and Layer 4 still fetches the
policy but reports its requirements as "required, not assessed" instead of judging
the code.

The regulatory layer is a pre-deployment check: it never inspects deployed entities,
it judges whether this repo would satisfy the org's policy if deployed. Applicability
mirrors the platform's own evaluator: a mitigation is "not applicable" only when the
repo has no model or LLM path at all, or when its target type (AgenticWorkflow for an
agent, TextGeneration for a plain LLM app, a predictive type for a scoring model) is
outside the check's applicable target types, for example drift or accuracy tracking on
an agent. A missing `datarobot.Deployment` never exempts a check, and calling the
DataRobot LLM Gateway directly does not either: the gateway is the model provider, the
deployment is the governed entity. For an agent or LLM app with no deployment, the
remedy is an agentic deployment (a CustomModel with target type AgenticWorkflow behind a
Deployment) that keeps using the gateway from inside. Only the active Pulumi configuration
counts: templates that ship selectable variants under `configurations/` deploy just the one
the symlink points at, and when an inactive variant already declares a Deployment the
report says to select it rather than build new infrastructure. A program that only
references a deployment owned elsewhere (`Deployment.get`) has those checks reported as
"provided by an existing deployment, verify there", never as passed.
If DataRobot
risk-management isn't reachable (feature not enabled for the org, no matching
policy), Layer 4 reports nothing and says why in the report's Engine Notes; tell the
user plainly that regulatory coverage was not assessed rather than implying it
passed. There is no local fallback checklist.

Invoke via the **Monitor tool if available**, so the developer sees each layer complete
as a live notification instead of a silent multi-minute wait. Fall back to Bash (same
output, shown at the end) on harnesses without a Monitor-equivalent.

Every stderr line is prefixed with `[mm:ss]` elapsed time, so a slow phase is visible
in the log. Filter the monitored output with **exactly** this pattern — do not narrow it:

```
grep -E --line-buffered "▶|✓|done \[|error|failed|traceback"
```

`▶` fires when a layer starts, `done [n/total]` after **every** finished check (the
user must see steady per-check movement through the long LLM phases — never filter
these out), and `✓` once per completed phase with its duration. The final `✓ HTML
report: file://…` (and `✓ Markdown report: …`) lines pass the same filter — always
relay them to the user, who otherwise has no way to know the report files exist.

```
echo "[uv] resolving scanner dependencies (first run downloads semgrep, ~1-2 min; cached after)…" >&2
uv run --with pip-audit --with semgrep \
  <skill_scripts_dir>/run_gap_analysis.py <repo> \
  --ref <ref>                    # optional
  --policy <path>                # optional
  --out gap-report.md            # Markdown report (a directory writes gap-report.md into it); the HTML report lands next to it
  --html <path>                  # optional: custom path for the HTML report
  --open                         # optional: open the HTML report in the browser
  --no-llm                       # optional: skip LLM checks (Layer 2, and Layer 4 evidence judging)
```

Keep the `echo` line: `uv` resolves the `--with` extras before Python starts and
prints nothing to a non-TTY until installation finishes, so on a cold cache the run
looks hung without it. The extras give Layer 1 dependency CVE and SAST scanning
(the secret scan and the engineering-baseline checks are built in); nothing is
installed globally. Dropping them still works, and the report says which scanners
were skipped.

Full flag reference (including `--fix`, `--select`, `--verify`, `--env-file`): run
`uv run <skill_scripts_dir>/run_gap_analysis.py --help`.

### 3. Summarize the report

Relay the `✓ HTML report: file://…` link the script printed (the browser is never
opened automatically), then read the written report back and summarize for the user:
- The composite finding count and severity breakdown.
- The **remediation posture** (Patch / Hybrid / Re-platform) and its one-line rationale.
  See [references/remediation-paths.md](references/remediation-paths.md) if the user
  asks why a posture was assigned.
- The three or four highest-severity findings, in plain language, with file:line
  evidence — never invent a finding; if a condition was skipped (e.g. a relational
  check missing one of its file groups), say so rather than guessing.

- Any regulatory (`POL-DR-*`) findings deserve their own framing: they come from the
  org's own DataRobot risk-management policy, and each one names the DataRobot
  platform feature that satisfies it plus how to enable it (Pulumi settings block,
  API/console step, or automatic on deployment). On a repo that already carries a
  pulumi-datarobot program, the IaC-satisfiable ones (drift/accuracy/fairness
  settings, notification policies, guards) are offered as assisted `--fix` edits to
  the Pulumi resources; the rest still mean adapting the architecture to deploy
  through DataRobot rather than treating them as code bugs to patch.

The developer can ask follow-up questions in this same conversation (why a condition
fired, what a specific fix changes, what a risk-management mitigation requires); the
skill running as a normal chat turn already grounds those answers in the same report
and codebase, no separate Q&A surface needed.

Regulatory (`POL-DR-*`) findings carry numbered fix steps and a docs link resolved at
run time from `docs.datarobot.com/llms.txt`, so links are never pinned in this skill.
When a finding shows "search docs.datarobot.com for ..." instead of a link, look the
topic up there yourself before advising; do not quote a page from memory.

### 4. Offer remediation

State the posture and let it drive the offer — the unit of decision is the *gap*, not
the whole agent:

- **PATCH** → offer to re-run with `--fix`. Plumbing fixes (secrets → env vars, model
  pins, CI/logging scaffolding) are surgical and safe.
- **HYBRID** → offer `--fix` for the plumbing now; flag which findings are structural
  and will need a targeted human review or a Re-platform pass later.
- **RE-PLATFORM** → too many structural gaps to patch safely in place. Read the
  posture text before recommending anything: it says whether the repo already builds
  on af-components and which agent framework it uses (also in the report header).

Ask **which** findings to fix: all auto-fixable, a selected subset (`--select
SEC-002,ITA-003`), or none. A blanket "fix everything" only ever applies
plumbing-classified fixes; business-logic fixes must be named explicitly.

**Safety rails, never skip these:**
- Fixes land on a new `gap-fixes/<timestamp>` branch, never the default branch. A
  GitHub URL is cloned to a scratch workspace; a local path is used as-is, so make
  sure its working tree is clean before running `--fix`.
- Nothing is pushed or opened as a PR without a **separate, explicit** approval after
  the developer has reviewed the diff.
- After `--fix`, offer `--verify` to re-score the fix branch and show a before/after
  deploy-readiness verdict.

### 5. Re-platform hand-off (structural gaps)

When the posture is Re-platform (or a post-fix rescore still shows structural gaps),
do not lead with `--fix`. Check two things the report already states, then choose:

- **Already on af-components** (the header lists `af-component-*` template sources):
  keep the application. The structural gap is that the agent or LLM path is not behind
  a DataRobot deployment, so propose adding a DataRobot agent deployment (a CustomModel
  behind a `datarobot.Deployment` in the Pulumi program) that guards and monitoring can
  attach to. Do not propose re-generating the repo.
- **Not on af-components**: hand off to the `datarobot-agent-assist` skill (design/code
  flow): it extracts the agent's business logic (prompts, tools, decision flow) into a
  reviewable `agent_spec.md` and scaffolds a governed replacement from it. **Show the
  spec and get explicit approval before anything is scaffolded.** Install
  `datarobot-agent-assist` if it isn't already, rather than scaffolding from inside
  this skill.

**Never change the agent framework unless the user asks.** The flavors the DataRobot
agent template offers are read at run time from the `af-component-agent` Copier
template (`agent_template_framework` choices), so the list is never hardcoded here.
A framework without a native flavor deploys through the template's generic Base
flavor, which wraps an arbitrary Python agent. The report header names the repo's
framework and which case applies.

Regulatory (`POL-DR-*`) findings feed this same path: a DataRobot-scaffolded
replacement gets the platform features those mitigations require (logging, tracing,
monitoring, guards, RBAC) largely by construction, so re-platforming is usually how
a repo full of unsatisfied risk-management mitigations becomes compliant.

---

## Reference material

- [references/pillars-and-layers.md](references/pillars-and-layers.md) — the 7-pillar /
  4-layer model, condition ID prefixes, and severity scale, to cite accurately in
  conversation.
- [references/policy-authoring.md](references/policy-authoring.md) — how a policy file
  overrides defaults, how to add a condition to the taxonomy, and how the
  regulatory layer sources its checks from DataRobot
  risk-management.
- [references/remediation-paths.md](references/remediation-paths.md) — how the
  Patch/Hybrid/Re-platform posture is computed, for when a user asks "why."
