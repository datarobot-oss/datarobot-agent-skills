# AIG-008 — Prompts not versioned/externalized

Determine whether system/instruction prompts are hardcoded inline in code with
no externalization or versioning. Large inline prompt strings scattered through
code (vs. a prompts/ directory or prompt registry) are the signal.

Report the file, line, and the inline prompt.

Output: follow `prompts/_contract.md`.
