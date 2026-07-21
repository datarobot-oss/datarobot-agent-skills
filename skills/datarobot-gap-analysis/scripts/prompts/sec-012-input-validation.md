# SEC-012 — Missing input validation on tool inputs & external data

Find tool/function entry points and external-data consumers that use their
inputs without type/range/schema validation. Look for tool functions that
accept raw `str`/`dict`/`Any` and pass them straight into side-effecting logic,
and external API responses consumed without checking shape/status.

Report the file, line, and the unvalidated input.

Output: follow `prompts/_contract.md`.
