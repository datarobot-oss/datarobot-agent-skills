# REL-004 — No graceful degradation / fallback path

Determine whether the system has fallback/degraded-mode behavior when a
dependency (model, API, datastore) is unavailable — e.g. cached response,
secondary provider, safe default. A hard failure with no fallback on a critical
path is the finding.

Report the file, line, and the critical path lacking a fallback.

Output: follow `prompts/_contract.md`.
