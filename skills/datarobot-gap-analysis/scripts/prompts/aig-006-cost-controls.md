# AIG-006 — No cost/token controls or rate limiting on model calls

Determine whether model calls have max-token caps, request/budget limits, or
rate limiting. Flag loops that call the model without bounds, missing
`max_tokens`, and absence of any rate limiter/budget guard.

Report the file, line, and the uncontrolled call.

Output: follow `prompts/_contract.md`.
