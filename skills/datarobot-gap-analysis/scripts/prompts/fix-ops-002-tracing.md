# Fix OPS-002 — Add tracing/telemetry scaffolding

Given the finding and the file, add minimal OpenTelemetry (or DataRobot agent
monitoring) instrumentation: initialize a tracer and wrap the main
agent/handler entry point in a span. Keep it dependency-light and clearly
marked; put exporter/endpoint wiring in `manual_followup`.

Output: follow `prompts/_fix_contract.md`.
