# Fix AIG-001 — Add guardrails around model I/O

Given the finding and the file, wrap the model call so inputs and outputs pass
through a guardrail step (moderation/PII/jailbreak check, output validation).
Prefer a minimal, dependency-light wrapper or the project's existing guardrail
utility if one exists; otherwise scaffold a clearly-marked guardrail function
with TODOs for provider wiring.

Output: follow `prompts/_fix_contract.md`.
