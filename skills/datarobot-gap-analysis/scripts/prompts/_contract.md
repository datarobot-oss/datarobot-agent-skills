# Shared Detection Output Contract

Every Layer-2 / Layer-4 detection prompt MUST return a single JSON object and
nothing else. The orchestrator parses this; prose outside the JSON breaks it.

```json
{
  "condition_id": "<the id being checked, e.g. SEC-001>",
  "status": "found | not_found | skipped",
  "skip_reason": "<only when status=skipped, e.g. 'relational pair incomplete'>",
  "findings": [
    {
      "file": "relative/path.py",
      "line": 42,
      "evidence": "short code excerpt or description — NEVER include a real secret value",
      "explanation": "why this is a gap",
      "confidence": "high | medium | low",
      "root_cause": "short label shared by every location with the same underlying defect",
      "severity_adjustment": "keep | lower",
      "severity_reason": "<only when lower: why this instance is less severe than the condition's default>"
    }
  ]
}
```

Rules for every detection prompt:
- Report only the file, line, and code path. **Never echo an actual secret value** —
  describe it (e.g. "OpenAI-style key assigned to `OPENAI_API_KEY`").
- If a relational check is missing one of its required file groups, return
  `status: "skipped"` with a `skip_reason` rather than guessing.
- Prefer precision over recall: if unsure, use `confidence: "low"` rather than omitting.
- Return at most 10 findings, the most consequential first. Locations that share
  a `root_cause` are ONE finding: cite the clearest location and name the others
  in `evidence` ("same pattern in tools/b.py, tools/c.py"). Never enumerate every
  parameter or every call site; the reply must stay short enough to finish.
- `line` may be null when the finding is file-level (e.g. "no tests anywhere").
- Files are shown with each line prefixed `N| `. Report that N as `line`, and put
  the exact code of that line (without the prefix) in `evidence` so it can be
  checked mechanically.
- A large file may be shown as an EXCERPT: its header, its definition lines, and
  windows around the lines that matter for this condition, with
  `… lines A-B omitted …` markers. Line numbers are the file's real ones. Never
  report on an omitted range; judge only the lines shown.
- Read the enclosing block before claiming something is unguarded: a `try/except`,
  validator, or allowlist a few lines above the cited line means it is guarded.
- A comment that explains why a guard exists ("timeout added to prevent a hang")
  is evidence the guard exists, not evidence the bug is live.
- Compensating controls elsewhere in the same file lower severity; say so with
  `severity_adjustment: "lower"` instead of reporting the default severity.
- When a file only delegates (a 3-line entrypoint calling `create_app()`), do not
  assert absence of what you could not see; use `confidence: "low"` or skip.
- Group locations that share one underlying defect under the same `root_cause`;
  the report merges them into a single finding.
- The section `REPO-WIDE EVIDENCE HINTS` lists grep hits from files you were not
  shown. Treat them as evidence that may already satisfy the condition.
