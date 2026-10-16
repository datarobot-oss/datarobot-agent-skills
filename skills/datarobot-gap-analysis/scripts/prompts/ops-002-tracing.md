# OPS-002 — No tracing/telemetry

Determine whether the code is instrumented for distributed tracing/telemetry
(OpenTelemetry, DataRobot agent monitoring, vendor tracing SDKs). Absence of
any span/trace/metric export is the finding.

Report the file, line (or `line: null` if repo-wide), and what is missing.

Output: follow `prompts/_contract.md`.
