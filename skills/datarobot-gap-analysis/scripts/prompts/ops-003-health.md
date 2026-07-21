# OPS-003 — No health checks / metrics endpoints

For services/apps, determine whether health/readiness and metrics endpoints
exist (e.g. `/health`, `/ready`, `/metrics`). Absence in a deployable service
is the finding. Pure libraries/CLIs may legitimately have none — use
`confidence: "low"` if unsure it's a service.

Output: follow `prompts/_contract.md`.
