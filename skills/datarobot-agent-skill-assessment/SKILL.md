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

## Example Usage

**Basic test:**
```
User: "Test the my-skill skill"
→ skill_dir="my-skill", improve=false
```

**Test and improve:**
```
User: "Assess and improve skills/data-processor"
→ skill_dir="skills/data-processor", improve=true, retest_after_improve=true
```

---

## Preconditions

1. Repository contains the target skill directory.
2. `DATAROBOT_API_TOKEN` is set in environment (or `.env` used by the tester runtime).
3. `datarobot-agent-tester` is installed and `dr-agent` CLI is available (or can be installed with user permission via `uv`).
4. Commands should be executed from the repository root directory (parent of `skills/`).
   If current directory is not repository root, `cd` to it first.

If any precondition fails, stop and return a clear error with remediation steps.

---

## Execution Steps

### 1) Normalize target path

- If input is `my-skill`, normalize to `skills/my-skill`.
- If input already starts with `skills/`, keep as-is.
- Verify directory exists.

If directory does not exist:
- Return Status: `NEEDS WORK`
- Error: `Skill directory not found: ${TARGET_SKILL_DIR}`
- List available skills:
  ```bash
  ls -d skills/*/
  ```
- Suggest user check spelling or provide correct path
- Stop execution

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

First verify `uv` is available:
```bash
uv --version >/dev/null
```

If not found:
- Return Status: `NEEDS WORK`
- Error: `uv package manager not found`
- Remediation: Install from https://github.com/astral-sh/uv
- Stop execution

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

### 4.5) Set reasonable timeouts

Testing may take time for complex skills. Set timeouts:
- Test command: 5 minutes
- Improve command: 10 minutes

If timeout exceeded:
- Kill process
- Return partial results with timeout note
- Status: `NEEDS WORK`

### 5) Run skill test

Run exactly:

```bash
dr-agent skills test --skill "${TARGET_SKILL_DIR}"
```

Capture stdout/stderr and exit code.

If exit code is non-zero:
- Set Status to `NEEDS WORK`
- Include full stderr in output
- Check if report was still generated (some testers write partial reports on failure)
- Continue to Step 6 to attempt report retrieval

### 6) Locate generated report

The tester writes reports to the current working directory with pattern:
`<skill-name>.skill-report.md` or timestamped variants.

Search for reports:
```bash
find . -maxdepth 2 -name "*skill-report.md" -type f
```

Identify the newest file by modification time:
```bash
ls -t *skill-report.md | head -n1
```

If no report found, check:
- Command output for error messages
- Whether test actually ran successfully (exit code 0)

Store path as `REPORT_FILE`.

Parse the report to extract:
- Overall test result (pass/fail)
- Number of test cases run
- List of failing test cases (if any)
- Key recommendations or issues

Store these for the Summary section.

### 7) Optional improve flow

If `improve=true`:

**Note**: The `improve` command will modify skill files in-place based on test findings.

Before running, inform the user:
"About to run improvement on ${TARGET_SKILL_DIR}. This will modify files. Continue? (yes/no)"

If user declines, skip to output and note improvement was skipped.

Before running improve:
- Store path to initial report as `INITIAL_REPORT`
- Note initial test results (pass/fail counts, scores if present)

Run:
```bash
dr-agent skills improve --skill "${TARGET_SKILL_DIR}"
```

Capture exit code. If non-zero, include error in output but continue to retest if requested.

If `retest_after_improve=true`, run:

```bash
dr-agent skills test --skill "${TARGET_SKILL_DIR}"
```

After retest:
- Store path to new report as `IMPROVED_REPORT`
- Compare:
  - Number of passing vs failing test cases
  - Specific issues resolved (diff the "Issues" sections)
  - New issues introduced
  - Overall score changes (if reports include numeric scores)

---

## Output Contract

Return all of the following sections:

1. **Status**
   - `PASS`: Test completed successfully, report generated, no critical errors
   - `NEEDS WORK`: Test failed, CLI unavailable, preconditions not met, or critical issues found in report
   
   Base status on:
   - Whether all commands executed successfully
   - Whether report was generated
   - Severity of issues in report (if it includes severity ratings)

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
