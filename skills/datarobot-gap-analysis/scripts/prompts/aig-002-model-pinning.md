# AIG-002 — Model not version-pinned (floating model id)

Find model identifiers that use a floating alias with no version/date suffix
(e.g. `gpt-4o`, `claude-sonnet`, `gemini-pro`) where behavior can drift when
the provider updates the alias. Distinguish from pinned ids that include a
date/version (e.g. `claude-sonnet-4-5-20250929`).

Report the file, line, and the floating model id (in `evidence`).

Output: follow `prompts/_contract.md`.
