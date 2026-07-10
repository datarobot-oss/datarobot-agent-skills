---
name: datarobot-agent-assist-simulate
description: >-
  Use when the user wants to adversarially test, evaluate, or harden an implemented AI agent before
  deployment; mentions swarm simulation, attack testing, persistence testing, evaluation criteria,
  or eval_report.md.
---

# Agent Assist — Simulate

Use this workflow to adversarially test an implemented agent before deployment.

This workflow reads `agent_spec.md` and any generated code (`tools.py`, `agent.py`) to run three
tracks of automated simulation, then iteratively hardens the agent through a convergence loop —
patching the system prompt automatically and, where prompt patching isn't sufficient, diagnosing
structural issues and offering targeted code fixes for user approval. All configuration is
collected through conversation before anything runs.

---

## Script Path Resolution

Before invoking the simulation script, resolve `<skill_scripts_dir>` once for the session:

- This `SKILL.md` file was loaded from a known path. Take that path, strip the filename, and that directory is `<this_skill_dir>`.
- `<skill_scripts_dir>` is `<this_skill_dir>/scripts/`.
- Confirm it exists: run `ls <this_skill_dir>/scripts/`. If missing, tell the user the skill installation is incomplete and stop.
- Use the resolved absolute path for every `<skill_scripts_dir>/...` reference in this skill.

**Python and dependency check (run once before the first script call):**

Resolve the Python binary to use — in order of preference:
1. If a `.venv/` directory exists in the working directory, use `.venv/bin/python3`
2. Otherwise use `python3`

Store the resolved binary as `<python>` and use it for all script calls.

Then confirm `pydantic_ai` is available:
```bash
<python> -c "import pydantic_ai, yaml" 2>/dev/null \
  || uv pip install pydantic-ai pyyaml 2>/dev/null \
  || <python> -m pip install pydantic-ai pyyaml 2>/dev/null \
  || pip3 install pydantic-ai pyyaml
```

Try `uv pip install` first (works in venv environments without pip). If all options fail, tell the user to run `pip install pydantic-ai pyyaml` in their terminal and stop.

---

## Pre-flight Check

1. Confirm `agent_spec.md` exists in the working directory. If not, tell the user and stop —
   this workflow requires a completed spec. Offer to switch to `agent-assist-build` to build one.
2. Confirm the spec has `system_prompt` and at least one tool defined. If either is missing,
   surface the gap and stop.
3. Check for generated code files: look for `tools.py` and `agent.py` in the working directory.
   Note which exist — these are potential targets for structural code fixes if unresolved
   scenarios require them and the user approves the changes after simulation.
4. Confirm `DATAROBOT_API_TOKEN` and `DATAROBOT_ENDPOINT` are set:
   ```bash
   env | grep -E "DATAROBOT_API_TOKEN|DATAROBOT_ENDPOINT"
   ```
   If either is missing, invoke the `datarobot-setup` skill before continuing. Do not print manual export instructions.

---

## Step 1 — Collect Configuration

Ask the following questions in sequence. Do not run the simulation until all answers are collected.
Save answers to `agent_config.yaml` automatically after collection.

**Question 1 — User type:**

Read `agent_spec.md` and derive 2–4 user personas specific to this agent's domain. Always append "Other — describe your user segment" as the last option:

> "Who are the primary users of this agent?
> 1. [derived persona 1]
> 2. [derived persona 2]
> ...
> N. Other — describe your user segment"

If the user picks "Other", ask: *"Describe your users in a sentence."* Pass the selected or entered persona description to `--user-type`.

**Question 2 — Grounding context (optional):**
> "Want to ground the behavior scenarios in real user data? Paste customer tickets, support logs,
> or a description of how your users typically behave — or say 'skip' to use defaults."

If the user provides text, save it to `user_context.txt` in the working directory and pass the
path to the script. If they skip, pass no context file.

**Question 3 — Iteration limit:**
> "How many times should I attempt to fix a failing scenario before marking it unresolved?
> Default is 3."

**Question 4 — Model:**
> "Which LLM should run the simulation? Default is anthropic/claude-sonnet-4-6. Say 'default' to keep it or paste a model ID from the LLM Gateway catalog."

**Question 5 — Evaluation mode:**
> "Standard breach detection (pass/fail) or scored evaluation using an LLM judge?
> Default is standard."

If `agent_config.yaml` already exists from a previous run, present the saved settings first:
> "Last time: [user_type], [iterations] iterations, [llm_judge_model], [judge_mode]. Same settings or change anything?"

---

## Step 2 — Generate and Review Scenarios

Run scenario generation:

```bash
<python> -u <skill_scripts_dir>/swarm_simulation.py agent_spec.md \
  --user-type <user_type> \
  --iterations <n> \
  --model <model> \
  --judge-mode <standard|scored> \
  [--context user_context.txt] \
  --generate-only
```

The script prints the generated scenario list grouped by track and writes the initial
`evaluation_criteria.md`. Tracks:
- **Attack** — tool misuse, scope bypass, data exfiltration, privilege escalation
- **Behavior** — confused users, contradictory inputs, edge cases
- **Persistence** — multi-turn escalation against restrictions found in the spec and implementation code

Present the full list to the user. Ask:
> "Does this look right? You can say 'add [description]' to include a scenario or 'remove [name]'
> to drop one. Say 'run it' when ready."

Apply any user additions or removals by editing `evaluation_criteria.md` directly using the Edit
tool before proceeding. Do not re-run generation — edit the file the script already wrote.

---

## Step 3 — Run Simulation

Once the user confirms, use the **Monitor tool** to stream progress live (fall back to Bash if Monitor is unavailable):

- **command:** `<python> -u <skill_scripts_dir>/swarm_simulation.py agent_spec.md --user-type "<user_type>" --iterations <n> --model <model> --judge-mode <standard|scored> [--context user_context.txt] --criteria evaluation_criteria.md`
- **description:** `swarm simulation progress`
- **timeout_ms:** `600000`
- **persistent:** `false`

Relay each notification line to the user as it arrives. Scenario results stream in as they complete:
```
[attack]      fetch_records scope bypass          ✓ passed
[attack]      data exfiltration via summary       ✗ breach
[behavior]    contradictory request               ✓ passed
[persistence] refund denial under pressure        ✗ breach
```

When you see `Simulation complete.` in the stream, the script has finished — proceed to Step 4.

The convergence loop runs automatically on failures. For each breach cluster the script prints:
```
──────────────────────────────────────────────
Fixing: <scenario name>
Reason: <breach summary>
Patch: <first 120 chars of system prompt addition>...
```

Patches are applied automatically without per-breach approval. Present the output as it arrives.

---

## Step 4 — Report, Spec Update, and Optional Structural Fixes

When the script finishes it prints a summary line and the path to `eval_report.md`.

Present the summary to the user:
- How many scenarios passed / total
- How many patches were applied
- How many scenarios remain unresolved (if any), with the structural recommendation for each

If patches were applied, `agent_spec.md` has been updated in-place with the hardened system prompt.
Tell the user: *"Your agent_spec.md has been updated with [N] system prompt patches. Full record in eval_report.md."*

If unresolved scenarios remain, prepare optional structural code fixes:

1. For each unresolved scenario, read its `**Recommendation:**` line from `eval_report.md`. The function to fix is embedded as `Function to fix: <name>` at the end of that line — extract it.
2. If a `function_hint` is present, search for it in `tools.py` first, then `agent.py`:
   ```bash
   rg -n "<function_hint>" tools.py agent.py
   ```
3. Present each unresolved scenario with its remaining risk, structural recommendation, and likely
   `<file>:<function>` target. Do not edit any implementation file yet.
4. Ask: *"Would you like me to implement these structural fixes?"* Stop and wait for explicit approval.
5. If approved, read the relevant sections and apply targeted fixes using the Edit tool. After each
   change, tell the user: *"Applied structural fix to `<file>:<function>` for [scenario name].
   Reason: [recommendation]."*
6. If declined, leave all implementation files unchanged.

After approved code fixes are applied, offer to re-run the simulation to verify:
> "Code fixes applied to [list of files]. Want me to re-run the simulation to confirm these scenarios now pass?"

If no `function_hint` is available for an unresolved scenario, surface the structural recommendation
to the user and explain that it requires a manually identified code change.

---

## Simulation Tracks — What Degrades Silently

| Track | Degrades when... |
|---|---|
| Attack | No tools defined — generates generic scenarios with no capability targeting |
| Behavior | No grounding context provided — falls back to generic user archetypes |
| Persistence | System prompt AND implementation code have no explicit restrictions (`only`, `never`, `cannot`, dollar limits) — both are scanned; sparse output only when neither has restrictions |

Surface these gaps to the user if relevant.

---

## After Simulation

Offer next steps:

```
What would you like to do next?
1. Review eval_report.md     — full transcript, patches applied, and unresolved scenarios
2. Re-run simulation         — after making further changes to the spec or code
3. Test locally              — run the agent on your machine before deploying
4. Deploy                    — deploy the hardened agent to DataRobot
```

- If **1**: read `eval_report.md` and present a structured summary to the user.
- If **2**: return to Step 1 to re-collect configuration (or reuse saved settings) and re-run.
- If **3**: read `AGENTS.md` for the local test command, display it in a code block, tell the user to run it in a new terminal. Do not run it yourself.
- If **4**: follow the deploy instructions in `agent-assist-build/SKILL.md`.
