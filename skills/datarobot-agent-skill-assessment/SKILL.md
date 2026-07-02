---
name: datarobot-agent-skill-assessment
description: >-
  Use when the user wants to assess and optionally improve a target skill directory using datarobot-agent-tester. 
  When datarobot-agent-tester is not installed, it installs via uv the datarobot-agent-tester 
  and calls an LLM ad judge to assess an skill via the installed dr-agent CLI. It requires DATAROBOT_API_TOKEN.
---

# Purpose

Given a target skill directory, run DataRobot Agent Tester to:
1. test the skill and produce a report
2. optionally improve the skill based on that report
3. optionally re-test and summarize before/after results

This skill requires a valid `DATAROBOT_API_TOKEN`.

---

## Inputs

- `skill_dir` (required): Path to the target skill directory under `skills/`.
  - Examples:
    - `my-skill`
    - `skills/my-skill`
- `improve` (optional, default: `false`): Whether to run improvement after testing.
  - Allowed: `true` / `false`
- `retest_after_improve` (optional, default: `true`): If `improve=true`, run test again and summarize deltas.
  - Allowed: `true` / `false`

---

## Preconditions

1. Repository contains the target skill directory.
2. `DATAROBOT_API_TOKEN` is set in environment (or `.env` used by the tester runtime).
3. `datarobot-agent-tester` is installed and `dr-agent` CLI is available (or can be installed with user permission via `uv`).

If any precondition fails, stop and return a clear error with remediation steps.

---

## Execution Steps

### 1) Normalize target path

- If input is `my-skill`, normalize to `skills/my-skill`.
- If input already starts with `skills/`, keep as-is.
- Verify directory exists.

Set:
- `TARGET_SKILL_DIR=<normalized path>`

### 2) Validate token

Run:

```bash
printenv DATAROBOT_API_TOKEN >/dev/null
```

If token missing, return:

- Error: `DATAROBOT_API_TOKEN is not set`
- Fix:
  - `export DATAROBOT_API_TOKEN=<your_token>`
  - or configure `.env` per project conventions

### 3) Check CLI availability

Run:

```bash
dr-agent --help >/dev/null
```

If success, continue to Step 5.

If failure, continue to Step 4.

### 4) Install datarobot-agent-tester
When `dr-agent --help` fails, the assistant must stop and ask the user to choose:

`datarobot-agent-tester` is not currently available (`dr-agent` not found).

Would you like me to install it using uv now?

Choose one option:
1) Project-only install (adds dependency to this repository):
   `uv add datarobot-agent-tester`

2) Global tool install (available system-wide):
   `uv tool install datarobot-agent-tester`

Reply with:
- `"1"` for project-only
- `"2"` for global
- `"no"` to skip installation

Rules:
- Do not run any install command before the user explicitly chooses.
- If user replies `"1"`, run:
  ```bash
  uv add datarobot-agent-tester
  ```
- If user replies `"2"`, run:
  ```bash
  uv tool install datarobot-agent-tester
  ```
- If user replies `"no"`, stop and return `NEEDS WORK` with remediation steps.

After install, re-check:
```bash
dr-agent --help >/dev/null
```
If still failing, return `NEEDS WORK` with command output.

### 5) Run skill test

Run exactly:

```bash
dr-agent skills test --skill "${TARGET_SKILL_DIR}"
```

Capture stdout/stderr and exit code.

### 6) Locate generated report

The tester writes a skill report file named with suffix `.skill-report.md`.
Find report(s) associated with `TARGET_SKILL_DIR` and identify the newest one.

If report cannot be found:
- Return command output and fail clearly.

### 7) Optional improve flow

If `improve=true`, run:

```bash
dr-agent skills improve --skill "${TARGET_SKILL_DIR}"
```

If `retest_after_improve=true`, run:

```bash
dr-agent skills test --skill "${TARGET_SKILL_DIR}"
```

Then locate newest report again and compare with pre-improvement report.

---

## Output Contract

Return all of the following sections:

1. **Status**
   - `PASS` or `NEEDS WORK`

2. **Install Mode**
   - `already-installed` | `uv-add` | `uv-tool-install` | `not-installed (user-declined)`

3. **Commands Run**
   - Exact commands executed, in order

4. **Artifacts**
   - Report file path(s)
   - Improvement command result (if run)

5. **Summary**
   - overall assessment
   - major issues
   - high-priority fixes

6. **Before/After Comparison** (only when improve+retest used)
   - What changed
   - What improved
   - Remaining gaps

---

## Guardrails

- Only act on the provided target skill directory.
- Do not modify unrelated files.
- Do not fabricate report contents.
- Keep outputs concise and actionable.
- Never install without explicit user confirmation.
