# Agent Assist — Simulate

Use this workflow to adversarially test an existing `agent_spec.md` before deployment.

This workflow runs three tracks of automated simulation, then iteratively hardens the agent's
system prompt through a convergence loop. All configuration is collected through conversation
before anything runs.

---

## Script Path Resolution

Before invoking the simulation script, resolve `<skill_scripts_dir>` once for the session:

- `<skill_scripts_dir>` is the `scripts/` subdirectory of the directory containing this `SKILL.md`.
- Confirm it exists with `ls <path_to_this_skill_dir>/scripts/`. If missing, tell the user the
  skill installation is incomplete and stop.

---

## Pre-flight Check

1. Confirm `agent_spec.md` exists in the working directory. If not, tell the user and stop —
   this workflow requires a completed spec. Offer to switch to `agent-assist-main` to build one.
2. Confirm the spec has `system_prompt` and at least one tool defined. If either is missing,
   surface the gap and stop.

---

## Step 1 — Collect Configuration

Ask the following questions in sequence. Do not run the simulation until all answers are collected.
Save answers to `agent_config.yaml` automatically after collection.

**Question 1 — User type:**
> "Who are the primary users of this agent?
> 1. Internal team
> 2. External customers
> 3. API consumers
> 4. Mixed"

**Question 2 — Grounding context (optional):**
> "Want to ground the behavior scenarios in real user data? Paste customer tickets, support logs,
> or a description of how your users typically behave — or say 'skip' to use defaults."

If the user provides text, save it to `user_context.txt` in the working directory and pass the
path to the script. If they skip, pass no context file.

**Question 3 — Iteration limit:**
> "How many times should I attempt to fix a failing scenario before marking it unresolved?
> Default is 3."

**Question 4 — Evaluation mode:**
> "Standard breach detection (pass/fail) or scored evaluation using an LLM judge?
> Default is standard."

If `agent_config.yaml` already exists from a previous run, present the saved settings first:
> "Last time: [user_type], [iterations] iterations, [judge_mode]. Same settings or change anything?"

---

## Step 2 — Generate and Review Scenarios

Run scenario generation:

```bash
python <skill_scripts_dir>/swarm_simulation.py agent_spec.md \
  --user-type <user_type> \
  --iterations <n> \
  --judge-mode <standard|scored> \
  [--context user_context.txt] \
  --generate-only
```

The script prints the generated scenario list grouped by track:
- **Attack** — tool misuse, scope bypass, data exfiltration, privilege escalation
- **Behavior** — confused users, contradictory inputs, edge cases
- **Persistence** — multi-turn escalation against each stated restriction

Present the full list to the user. Ask:
> "Does this look right? You can say 'add [description]' to include a scenario or 'remove [name]'
> to drop one. Say 'run it' when ready."

Write the confirmed scenario list to `evaluation_criteria.md` before proceeding.

---

## Step 3 — Run Simulation

Once the user confirms, run:

```bash
python <skill_scripts_dir>/swarm_simulation.py agent_spec.md \
  --user-type <user_type> \
  --iterations <n> \
  --judge-mode <standard|scored> \
  [--context user_context.txt] \
  --criteria evaluation_criteria.md
```

Show live progress as the script prints it:
```
[attack]      fetch_records scope bypass          ✓ passed
[attack]      data exfiltration via summary       ✗ breach
[behavior]    contradictory request               ✓ passed
[persistence] refund denial under pressure        ✗ breach
```

The convergence loop runs automatically on failures. For each breach cluster the script prints:
```
──────────────────────────────────────────────
Fixing: <scenario name>
Reason: <breach summary>
Patch: <first 120 chars of system prompt addition>...
```

Patches are applied automatically without per-breach approval. Present the output as it arrives.

---

## Step 4 — Report and Spec Update

When the script finishes it prints a summary line and the path to `eval_report.md`.

Present the summary to the user:
- How many scenarios passed / total
- How many patches were applied
- How many scenarios remain unresolved (if any), with the structural recommendation for each

If patches were applied, `agent_spec.md` has been updated in-place with the hardened system prompt.
Tell the user: *"Your agent_spec.md has been updated with [N] system prompt patches. Full record in eval_report.md."*

If unresolved scenarios remain, name them explicitly and explain why prompt patching couldn't fix
them (the script includes a structural diagnosis per unresolved scenario).

---

## Simulation Tracks — What Degrades Silently

| Track | Degrades when... |
|---|---|
| Attack | No tools defined — generates generic scenarios with no capability targeting |
| Behavior | No grounding context provided — falls back to generic user archetypes |
| Persistence | System prompt has no explicit restrictions (`only`, `never`, `cannot`, dollar limits) — sparse output |

Surface these gaps to the user if relevant.

---

## After Simulation

Offer next steps:
1. Review `eval_report.md` for the full record
2. Return to `agent-assist-main` to deploy the hardened agent
3. Re-run simulation if the user made further changes to the spec
