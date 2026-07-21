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
      "confidence": "high | medium | low"
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
- `line` may be null when the finding is file-level (e.g. "no tests anywhere").
