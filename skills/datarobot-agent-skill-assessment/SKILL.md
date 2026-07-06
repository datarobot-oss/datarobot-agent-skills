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
5. Target skill directory must contain at minimum:
   - A markdown file (`.md`) with skill instructions
   - OR a `skill.yaml` / `skill.json` configuration file
   
   If directory exists but contains no recognizable skill files:
   - Status: `NEEDS WORK`
   - Error: `Directory exists but does not appear to contain a valid skill`
   - List directory contents for debugging

If any precondition fails, stop and return a clear error with remediation steps.

---

## Execution Steps

### 1) Verify and set working directory

Check if current directory is repository root:
```bash
if [ -d "skills" ]; then
  echo "Already in repository root"
else
  # Attempt to find repository root
  if [ -d "../skills" ]; then
    cd ..
  elif [ -d "../../skills" ]; then
    cd ../..
  else
    # Return error
    echo "Cannot locate repository root (no skills/ directory found)"
    exit 1
  fi
fi
```

If `skills/` directory not found after navigation:
- Status: `NEEDS WORK`
- Error: `Cannot locate repository root. Please run from a directory containing skills/`
- Stop execution

### 1.1) Normalize target path

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

### 4.5) Set command timeouts

Use `timeout` command (GNU coreutils) to enforce limits:
- Test command: 300 seconds (5 minutes)
- Improve command: 600 seconds (10 minutes)

Example:
```bash
timeout 300 dr-agent skills test --skill "${TARGET_SKILL_DIR}"
EXIT_CODE=$?
```

If exit code is 124 (timeout):
- Status: `NEEDS WORK`
- Error: `Command exceeded timeout limit`
- Include partial output if available
- Stop execution

If `timeout` command not available (e.g., macOS without GNU coreutils):
- Log warning: "Timeout enforcement unavailable, commands may run indefinitely"
- Continue without timeout

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

Extract skill name from `TARGET_SKILL_DIR`:
```bash
SKILL_NAME=$(basename "${TARGET_SKILL_DIR}")
```

Search for reports matching this skill:
```bash
find . -maxdepth 2 -name "${SKILL_NAME}*.skill-report.md" -o -name "*${SKILL_NAME}*skill-report.md" | head -n1
```

If multiple matches found, select newest by modification time:
```bash
ls -t ${SKILL_NAME}*.skill-report.md 2>/dev/null | head -n1
```

If no report found, check:
- Command output for error messages
- Whether test actually ran successfully (exit code 0)

Store path as `REPORT_FILE`.

Parse the report using these strategies:
- Look for markdown headers like `## Summary`, `## Test Results`, `## Issues`
- Extract pass/fail counts from lines matching patterns like:
  - `Passed: X/Y tests`
  - `✓ X passed, ✗ Y failed`
- Identify failing tests from bullet lists or tables under "Failed Tests" or "Issues" sections
- If report format is unclear, include the first 50 lines of the report in output for user review

Store extracted data as:
- `TOTAL_TESTS=<number>`
- `PASSED_TESTS=<number>`
- `FAILED_TESTS=<number>`
- `FAILING_TEST_NAMES=<list>`

### 7) Optional improve flow

If `improve=true`:

**Note**: The `improve` command will modify skill files in-place based on test findings.

Before running improve:
- Inform user: "About to run improvement on ${TARGET_SKILL_DIR}. This will modify files in-place. Continue?"
- Wait for explicit response

If user responds with "no", "n", "skip", or declines:
- Skip improvement step
- Jump to Output Contract
- In Summary section, note: "Improvement skipped by user request"

If user responds with "yes", "y", or confirms:
- Proceed with improve command

If response is unclear:
- Ask again: "Please respond 'yes' to continue or 'no' to skip improvement"

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

Generate Before/After comparison:

1. **Test counts comparison:**
   ```
   Before: X passed, Y failed (Z total)
   After:  A passed, B failed (C total)
   Delta:  +/- N passing
   ```

2. **Issue-level diff:**
   - Extract issue lists from both reports (look for bullet points under "Issues" or "Failures")
   - Identify resolved issues (present in INITIAL_REPORT but not IMPROVED_REPORT)
   - Identify new issues (present in IMPROVED_REPORT but not INITIAL_REPORT)
   - Identify persistent issues (present in both)

3. **File changes:**
   ```bash
   git diff --stat "${TARGET_SKILL_DIR}" 2>/dev/null || echo "Git not available for diff"
   ```

If retest shows degradation (more failures after improve):
- Highlight this prominently in Summary: "⚠️ Improvement resulted in MORE failing tests"
- List newly introduced failures
- Suggest: "Consider reverting changes and reviewing improve command output for errors"
- Status should be `NEEDS WORK`

Include all three sections in "Before/After Comparison" output.

---

## Output Contract

Return all of the following sections:

1. **Status**
   - `PASS`: Test completed successfully, report generated, no critical errors
   - `NEEDS WORK`: Test failed, CLI unavailable, preconditions not met, or critical issues found in report
   
   **Status determination logic:**

   Set `NEEDS WORK` if ANY of:
   - Target skill directory not found
   - DATAROBOT_API_TOKEN not set
   - CLI installation failed or was declined
   - Test command exited with non-zero code AND no report generated
   - Report contains issues marked "critical" or "high severity" (if severity ratings present)
   - Command timeout occurred

   Set `PASS` if ALL of:
   - All commands executed successfully (exit code 0)
   - Report was generated
   - No critical/high-severity issues (or report doesn't include severity ratings)

   When in doubt (e.g., test passed but report shows warnings), default to `PASS` and include warnings in Summary.

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

## Example Output

**Scenario: Test-only run with issues found**

```
**Status**: NEEDS WORK

**Install Mode**: already-installed

**Commands Run**:
1. `dr-agent skills test --skill "skills/my-skill"`

**Artifacts**:
- Report: `./my-skill.skill-report.md`

**Summary**:
Test completed but found 3 failing test cases:
- `test_input_validation`: Missing required field validation
- `test_error_handling`: Unhandled exception for null inputs
- `test_output_format`: Output missing 'timestamp' field

High-priority fixes:
1. Add input validation for required fields (line 45)
2. Wrap processing logic in try-catch (line 78)
3. Include timestamp in output schema (line 120)

**Before/After Comparison**: N/A (improve not run)
```

---

## Troubleshooting

**"Command not found: dr-agent" after installation**
- If installed with `uv tool install`, ensure `~/.local/bin` is in PATH
- Try: `uv tool run dr-agent --help`

**"Report not found" after successful test**
- Check current directory: `pwd`
- List all .md files: `find . -name "*.md"`
- Report may have unexpected name; include find output in error message

**Timeout on large skills**
- Increase timeout values in Step 4.5
- Or run test command manually without timeout to see full execution time

**Token authentication fails**
- Verify token format (should be alphanumeric string)
- Test token: `curl -H "Authorization: Bearer $DATAROBOT_API_TOKEN" <api-endpoint>`

---

## Guardrails

- Only act on the provided target skill directory.
- Do not modify unrelated files.
- Do not fabricate report contents.
- Keep outputs concise and actionable.
- Never install without explicit user confirmation.
