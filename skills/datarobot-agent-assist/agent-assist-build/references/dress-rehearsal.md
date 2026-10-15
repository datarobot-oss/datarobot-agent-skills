## Dress Rehearsal

### What it is

Dress rehearsal simulates your `agent_spec.md` **before any code is written**. Think of it as a preview performance:

| Aspect | Dress rehearsal | After coding |
|--------|-----------------|--------------|
| Agent responses | Real LLM via DataRobot Gateway | Real LLM in your app |
| Tool calls | **Simulated** return values (no real APIs) | Real integrations |
| Purpose | Validate prompts, tools, and UX early | Production use |

You play the **end user**. The rehearsal script drives the LLM, simulates tool outputs, and formats session output. You orchestrate the loop, handle out-of-character commands, and produce a shareable Markdown report at the end.

**Engine location:** `<skill_scripts_dir>/rehearsal.py`

**Report location:** `<target_dir>/rehearsal_report/rehearsal_report.md` (latest); archived copy at `<target_dir>/.datarobot/rehearsal/<session_id>/rehearsal_report.md`

### Initial prompt (design phase)

Before transitioning to coding, explain dress rehearsal briefly, then ask (exact wording):

> **Dress rehearsal** is a try-before-you-build session: you chat with your agent design as if it were already running. The agent uses your spec's model and system prompt; tool calls return **simulated** (fake but realistic) data — no real APIs, no deployment, no code written yet. It's a safe way to test prompts, tools, and conversation flow before implementation.
>
> Would you like to run a dress rehearsal simulation first? (recommended)

Wait for their reply:

- **If yes** — follow this document end to end. Do not substitute improvised role-play or manual mock tool traces.
- **If no** (or any decline such as "no", "skip", "not now") — go to **[Post-design next steps](../SKILL.md#post-design-next-steps)**. Do not jump to coding, framework selection, or template setup.

### Visual presentation (required)

Rehearsal must look visually distinct from normal design/coding chat. Display rehearsal output **verbatim from the first line to the last** — do not truncate, summarize, or replace the closing lines. Each turn is wrapped with a symmetric `─ ★ Agent Dress Rehearsal ★ ─` line at the **top and bottom**, followed by continuation hints and `Type DONE to end the rehearsal session.` **Do not** rephrase those hints in your own words.

While a rehearsal session is active:

- **Announce entry** before the first rehearsal output: e.g. *"Starting dress rehearsal session"*
- **Do not mix** normal design/coding commentary into rehearsal turns — keep rehearsal in its own lane until the feedback report

### Step 1 — Initialize the session

```bash
python <skill_scripts_dir>/rehearsal.py --init --spec <target_dir>/agent_spec.md --target-dir <target_dir>
```

If `agent_spec.md` does not exist and no path was provided, say so and stop.

The script creates a session directory at `<target_dir>/.datarobot/rehearsal/<session_id>/` and prints two lines:
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

**On each user message:**

- If it starts with `NOTE:` — strip the prefix, persist the note, acknowledge briefly, and prompt for the next message:

```bash
python <skill_scripts_dir>/rehearsal.py --session {session_dir} --note "{note_text}"
```

Do **not** call the turn command for `NOTE:` messages.

- If it is `DONE` — **immediately** run report generation (mandatory — do this before any summary, menu, or post-design steps):

```bash
python <skill_scripts_dir>/rehearsal.py --report --session {session_dir}
```

Equivalent: `python <skill_scripts_dir>/rehearsal.py --session {session_dir} "DONE"`

Do **not** show **[Post-design next steps](../SKILL.md#post-design-next-steps)** until `report=` appears in the script output and `<target_dir>/rehearsal_report/rehearsal_report.md` exists. Then continue to [Step 3](#step-3--feedback-report).

- Otherwise — run the turn:

```bash
python <skill_scripts_dir>/rehearsal.py --session {session_dir} "{user_message}"
```

`--target-dir` is optional on turns — the session stores it from `--init`. You may pass `--target-dir <target_dir>` again to override.

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

Step 2 should already have run `--report` (or `"DONE"`) and created the base report file. If the file is missing, run:

```bash
python <skill_scripts_dir>/rehearsal.py --report --session {session_dir}
```

Optional flags:

- `--transcript full` — include full tool-call arguments and simulated JSON returns (default: summary)
- `--output <path>` — override the default `<target_dir>/rehearsal_report/rehearsal_report.md`

The script prints:
```
report=<path>
archive=<session_archive_path>
turns=<count>
tool_invocations=<count>
```

Then review the session and consider each of these areas — only surface the ones where you have something concrete to say:

- **System prompt** — wording, missing constraints, persona, tone
- **Tools** — input/output scoping, missing or redundant tools, argument naming
- **Model** — only flag if clearly wrong for the observed task complexity
- **Example prompts** — additions or revisions based on what was tested
- **Other** — edge cases, UX concerns, data dependency risks

Replace the placeholder `## Suggested Changes` section in `<target_dir>/rehearsal_report/rehearsal_report.md` with numbered, actionable recommendations. If nothing needs changing, write `No changes recommended.`

Tell the user (2–3 sentences max):

- What was tested and how the agent performed overall
- That the full report is saved at `<target_dir>/rehearsal_report/rehearsal_report.md` and can be shared with QA, product, and data science

Then offer to implement any changes to `agent_spec.md`. If you apply spec changes, append a `## Spec Updates Applied` section to the report listing each change in bullet form (what changed and why — not a unified diff).

After applying changes (or if none are needed), go to **[Post-design next steps](../SKILL.md#post-design-next-steps)**.
