# OPS-001 — No structured logging / audit trail of agent actions

Determine whether the agent records its actions and tool calls in a structured,
auditable form (structured logger, JSON logs, audit events). Flag reliance on
bare `print()` or no logging at all, and absence of an action/tool-call audit
trail.

Report the file, line, and what is missing.

Output: follow `prompts/_contract.md`.
