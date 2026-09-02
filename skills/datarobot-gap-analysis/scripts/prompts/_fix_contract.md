# Shared Fix Output Contract (assisted fixes)

Assisted-fix prompts receive a single finding (file, line, evidence) plus the
current content of the target file. They MUST return a single JSON object that
the remediation engine applies as an edit on the fix branch — never to the
user's default branch.

```json
{
  "condition_id": "SEC-011",
  "file": "relative/path.py",
  "can_fix": true,
  "explanation": "what the change does and why it closes the gap",
  "edits": [
    {
      "old_string": "exact substring to replace (must be unique in the file)",
      "new_string": "replacement"
    }
  ],
  "new_files": [
    { "path": "relative/new_file.py", "content": "full file content" }
  ],
  "manual_followup": "anything the human must still do (e.g. set an env var, rotate the key)"
}
```

Rules:
- Preserve the file's existing style, imports, and indentation.
- `old_string` must match the source EXACTLY and be unique; prefer the smallest
  unambiguous span.
- Make the minimal change that closes the gap — do not refactor unrelated code.
- If you cannot produce a safe automatic fix, return `can_fix: false` with an
  `explanation`; the engine will downgrade it to advisory guidance.
- Never introduce a real secret value. When removing a hardcoded secret, replace
  it with an env-var/config reference and note the rotation step in
  `manual_followup`.
