## Dress Rehearsal

### What it is

Dress rehearsal simulates your `agent_spec.md` **before any code is written**. Think of it as a preview performance:

| Aspect | Dress rehearsal | After coding |
|--------|-----------------|--------------|
| Agent responses | Real LLM via DataRobot Gateway | Real LLM in your app |
| Tool calls | **Simulated** return values (no real APIs) | Real integrations |
| Purpose | Validate prompts, tools, and UX early | Production use |

You play the **end user**. The rehearsal script drives the LLM, simulates tool outputs, and formats session output. You orchestrate the loop, handle out-of-character commands, and produce the feedback report at the end.

**Engine location:** `<skill_scripts_dir>/rehearsal.py`

### Visual presentation (required)

Rehearsal must look visually distinct from normal design/coding chat. Display rehearsal output **verbatim from the first line to the last** — do not truncate, summarize, or replace the closing lines. Each turn is wrapped with a symmetric `─ ★ Agent Dress Rehearsal ★ ─` line at the **top and bottom**, followed by continuation hints and `Type DONE to end the rehearsal session.` **Do not** rephrase those hints in your own words.

While a rehearsal session is active:

- **Announce entry** before the first rehearsal output: e.g. *"Starting dress rehearsal session"*
- **Do not mix** normal design/coding commentary into rehearsal turns — keep rehearsal in its own lane until the feedback report

### Step 1 — Initialize the session

```bash
python <skill_scripts_dir>/rehearsal.py --init [--spec agent_spec.md]
```

If `agent_spec.md` does not exist and no path was provided, say so and stop.

The script creates a unique session directory in the system temp dir and prints two lines:
```
session=<session_dir>
output=<output_file>
```

Retain `session_dir` for all subsequent calls. Read the `output_file` and display its contents **verbatim**, then say:

> You are now the **end user** of this agent. Type messages as a real user would.
>
> **Out-of-character commands:**
> - `NOTE: <text>` — record a design observation
> - `DONE` — end the session and generate your feedback report

### Step 2 — Simulation loop

Keep track of any notes and the number of turns as the session progresses — you'll need these for the report.

**On each user message:**

- If it starts with `NOTE:` — acknowledge the note, prompt for next message. Do not call the script.
- If it is `DONE` — proceed to Step 3.
- Otherwise — run the turn:

```bash
python <skill_scripts_dir>/rehearsal.py --session {session_dir} "{user_message}"
```

The script prints `output=<output_file>`.

**CRITICAL — display rule for each turn:** Your user-visible reply for that turn must be **only** the full contents of `output_file` (every line, start to finish). Do not append commentary, performance notes, or your own NOTE/DONE instructions.

Before sending, verify the output includes **both** turn decorations (the symmetric `★ Agent Dress Rehearsal ★` line at top **and** bottom). If the bottom decoration is missing from your reply, you truncated the file — re-read `output_file` and display it complete.

**Wrong** (never do this after a turn):
```
[Agent]: ...response...

This time the agent called 3 tools in parallel... Type DONE to end the session.
```

**Correct** — show the entire file, ending with:
```
─────────★ Agent Dress Rehearsal ★─────────
Type your next message to continue.
Use NOTE: <text> to record a design observation.
Type DONE to end the rehearsal session.
```

The file will contain `[TOOL CALL]`, `[SIMULATED RETURN]`, and `[Agent]` sections as appropriate.

If the script exits non-zero, display the error and ask whether to continue or abort. If rehearsal output includes a `[Model]` section, relay it to the user — the script already picked an available model automatically; do not ask the user to choose a model or paste raw API 404 JSON.

### Step 3 — Feedback report

Before writing the report, review the session and consider each of these areas — only surface the ones where you have something concrete to say:

- **System prompt** — wording, missing constraints, persona, tone
- **Tools** — input/output scoping, missing or redundant tools, argument naming
- **Model** — only flag if clearly wrong for the observed task complexity
- **Example prompts** — additions or revisions based on what was tested
- **Other** — edge cases, UX concerns, data dependency risks

Then write the report in this format:

```
════════════════════════════════════════════
  DRESS REHEARSAL REPORT
════════════════════════════════════════════

{1–2 sentences: what was tested and how the agent performed overall}
{If notes were recorded: "Notes: " followed by each note on its own line, prefixed with —}

Suggested changes:
1. {specific, actionable change}
2. {specific, actionable change}
…
{If nothing worth changing: "No changes recommended."}

════════════════════════════════════════════
```

Then offer to implement any changes to `agent_spec.md`. After applying changes (or if none are needed), go to **[Post-design next steps](../SKILL.md#post-design-next-steps)**.
