## Resume Design

Resume **[1. Designing an AI Agent](../SKILL.md#1-designing-an-ai-agent)** on an existing `agent_spec.md` in `<target_dir>`. Read the spec, classify its state, start at the matching Design section, and **run that section and every section after it in order** — do not skip ahead to coding or template setup.

---

### When to use

- The user enters **Design** (menu option 1) and continues an existing spec ([workspace-resolution](workspace-resolution.md))
- The user chooses to edit the spec from [Spec issues](pre-coding-checklist.md#spec-issues) during pre-coding

**Not** Resume Design — use the [Post-design review loop](#exceptions) instead (Post-design menu option 2).

---

### Entry paths

| Entry | Before resuming |
|-------|-----------------|
| **Design menu** — continue existing spec | Set `<design_to_code>` = false |
| **Pre-coding** — Spec issues → edit spec | Set `<design_to_code>` = false; stop the [pre-coding checklist](pre-coding-checklist.md); do not edit `agent_spec.md` inline during pre-coding |

After Design finishes (via Agent Simulation → Post-design next steps), coding may resume only when the user chooses **Code the agent** (set `<design_to_code>` = true and re-enter the [pre-coding checklist](pre-coding-checklist.md)).

---

### Spec complete

Canonical definition used by [Bootstrap step 2](pre-coding-checklist.md#bootstrap) (cold Code entry — **validation only**, does not start Resume Design) and the resume table below. A spec is **complete** when all of the following hold:

| Field | Requirement |
|-------|-------------|
| `model` | Set (non-empty) |
| `llm_deployment_id` | Set **only if** `model` is the `datarobot-deployed-llm` placeholder; otherwise absent or empty |
| `system_prompt` | Non-empty |
| `frontend.type` | Set |
| `tools` | Key **present** in YAML — either one or more tool entries, or `tools: []` |

**`llm_deployment_id` rule:** the placeholder model is shared by every DataRobot-deployed LLM, so on its own it does not name one. A spec carrying it without an id is **not** complete — route to [Model Selection](../SKILL.md#model-selection) to re-pick the deployment. Template setup refuses that pair anyway; catching it here keeps the failure in the design phase.

**`tools` rules:**

- **Missing `tools` key** ≠ complete. Route to [Spec Display](../SKILL.md#spec-display) to add tools (or confirm none in Design).
- **`tools: []`** is valid only after the user **explicitly confirms no tools are needed** — during Design or via pre-coding [Spec issues](pre-coding-checklist.md#spec-issues) choice 2. Write `tools: []` to `agent_spec.md` when that confirmation happens during pre-coding.

---

### Classify spec state

Read `<target_dir>/agent_spec.md` and evaluate **top to bottom**; use the **first matching row** in the [resume table](#resume-table). If multiple gaps exist, the first row still wins (earliest Design section).

| Check | Treat as |
|-------|----------|
| File empty or no meaningful YAML content | Spec empty |
| `system_prompt` key missing, or value empty / whitespace-only | Empty or missing `system_prompt` |
| `model` key missing or empty | Missing `model` |
| `model` is the `datarobot-deployed-llm` placeholder and `llm_deployment_id` is missing or empty | Missing `llm_deployment_id` |
| `frontend.type` not set | Missing `frontend.type` |
| `tools` key absent | Missing `tools` |
| All [spec complete](#spec-complete) requirements met | Complete |

---

### Resume table

| State of `agent_spec.md` | Start at | Sections that follow (in order) |
|--------------------------|----------|----------------------------------|
| Spec empty | [Clarification Phase](../SKILL.md#clarification-phase) | Model Selection → Frontend Check → Spec Display → Agent Simulation → Post-design next steps |
| Empty or missing `system_prompt` | [Clarification Phase](../SKILL.md#clarification-phase) | Model Selection → Frontend Check → Spec Display → Agent Simulation → Post-design next steps |
| Missing `model` only | [Model Selection](../SKILL.md#model-selection) | Frontend Check → Spec Display → Agent Simulation → Post-design next steps |
| Missing `llm_deployment_id` (placeholder `model`, no id) | [Model Selection](../SKILL.md#model-selection) | Frontend Check → Spec Display → Agent Simulation → Post-design next steps |
| Missing `frontend.type` only | [Frontend Check](../SKILL.md#frontend-check) | Spec Display → Agent Simulation → Post-design next steps |
| Missing `tools` only (`tools` key absent) | [Spec Display](../SKILL.md#spec-display) | Agent Simulation → Post-design next steps |
| [Complete](#spec-complete) | [Spec Display](../SKILL.md#spec-display) | Agent Simulation → Post-design next steps |

**Section chain rules:**

- **Frontend Check** — skip when `frontend.type` is already set in `agent_spec.md` (same as [SKILL.md](../SKILL.md#frontend-check)).
- **Agent Simulation** — always run after Spec Display on this path (dress rehearsal offer), unless the [Post-design review loop](#exceptions) applies.

### Spec Display → Agent Simulation (required transition)

On every Resume Design path, [Spec Display](../SKILL.md#spec-display) is **not** the end of design — even when the spec becomes [complete](#spec-complete) during that section (e.g. adding the missing `tools` key after pre-coding [Spec issues](pre-coding-checklist.md#spec-issues)).

**After showing the spec:**

- Invite refinement only (system prompt, tools, model, examples). Follow [SKILL.md § Spec Display](../SKILL.md#spec-display) — one design gate per turn.
- Do **not** ask about coding, template setup, or "proceeding to coding" in the same turn or as an alternative to refinement. Completing the spec does **not** authorize skipping to coding.

**When the user is done refining** (e.g. "looks good", "specs looks good", "no changes", "move on"):

- In your **next** response, go directly to [Agent Simulation (Before Coding)](../SKILL.md#agent-simulation-before-coding) — present the dress-rehearsal prompt using the exact wording in SKILL.md.
- Do **not** offer [Post-design next steps](../SKILL.md#post-design-next-steps) yet. The coding option appears only **after** the user declines dress rehearsal or finishes a rehearsal session.

**Wrong (do not do this on Resume Design):**

> The spec is now complete. Would you like to refine anything, or shall I proceed to coding?

**Right:** refinement invite only → user confirms → dress-rehearsal offer → (if declined) Post-design next steps menu.

---

### Exceptions

**Post-design review loop** — when the user chooses **Review / edit spec** from [Post-design next steps](../SKILL.md#post-design-next-steps): stay in [Spec Display](../SKILL.md#spec-display) only, then return to the Post-design menu. Do **not** re-run Resume Design, Clarification, Model Selection, Frontend Check, or Agent Simulation unless the user leaves and re-enters via an entry path above.
