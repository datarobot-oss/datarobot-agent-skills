# Fix OPS-001 — Add structured logging

Given the finding and the file, replace bare `print()` calls used for
operational output with a structured logger, or introduce a module-level logger
if none exists. Keep messages equivalent. Do not log secrets.

Output: follow `prompts/_fix_contract.md`.
