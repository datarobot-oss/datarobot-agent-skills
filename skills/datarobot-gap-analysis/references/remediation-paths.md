# Remediation Path Determination

Fix-in-place vs. rebuild-from-scratch is a false binary. The unit of decision is the
**gap**, not the agent. Plumbing gaps (secrets, unpinned models, missing scaffolding)
patch safely; **structural** gaps (no observability, no guardrails, human/shared
identity, no resilience) cannot be surgically fixed, "fixing" them means restructuring
business logic someone else owns. When structural gaps dominate, lifting the business
logic into a fresh, conformant base is safer than in-place surgery.

## How a condition becomes "structural"

A condition in `taxonomy.yaml` is structural when either:
- It is explicitly flagged `structural: true`, or
- Its `fix_type` is `advisory` **and** its severity is `high` or `critical` (an advisory
  finding has no automated fix by definition; at high/critical severity there is no
  safe way to leave it alone either).

## Scoring

Each finding is weighted by severity (critical=4, high=3, medium=2, low=1). The
**structural score** is `structural_weight / total_weight` across all findings in the
run.

## The three postures

| Posture | Condition | Meaning |
|---|---|---|
| **PATCH** | Structural score ≤ 0.25 | Only a small share of weighted risk is structural. Fixes are surgical and low-risk to existing business logic. |
| **HYBRID** | Structural score between 0.25 and 0.50, and fewer than 4 high/critical structural findings | Mixed profile. Automated fixes handle the plumbing now; flagged structural items need targeted human review, or a later Re-platform pass, before a clean rescore. |
| **RE-PLATFORM** | Structural score ≥ 0.50, **or** 4+ high/critical structural findings (an absolute override, so a small repo that is almost entirely structural doesn't get missed by density alone) | Structural risk is pervasive. Patching means restructuring code you don't own. Extract the business logic into a fresh base instead of restructuring in place. |

Every posture ships with a plain-language rationale naming the count of structural
findings and the weighted-risk percentage, so the recommendation is never a bare label.

## Thresholds are policy, not code

`patch_max`, `replatform_min`, and the absolute structural-count override all live
under `posture:` in the policy file (see
[policy-authoring.md](policy-authoring.md)) and can be tuned per org without a code
change.

## Re-platform mechanics

1. **Extract** — the business logic (system prompt, tools, decision flow) is lifted
   into a structured, human-readable `agent_spec.md`.
2. **Human review gate** — the spec, not a code diff, is the checkpoint. Nothing is
   scaffolded until the developer approves it. This is what makes the path safe when
   the codebase under analysis isn't one this skill (or the developer running it)
   originally wrote.
3. **Scaffold** — on approval, the spec is the input to `datarobot-agent-assist`'s
   coding flow, which scaffolds a governed agent from it using the DataRobot
   application-framework stack.
4. **Rescore** — re-run the assessment against the scaffolded agent to confirm the
   structural gaps are closed.
