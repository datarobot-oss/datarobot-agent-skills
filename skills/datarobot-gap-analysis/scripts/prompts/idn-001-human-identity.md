# IDN-001 — Agent authenticates as a human / shared account

Examine how the agent authenticates. Determine whether it uses a personal
access token, a human user's OAuth token, or a single shared service account,
rather than its own dedicated workload/agent identity. Report the file, line,
and what identity type is being used.

Signals: hardcoded personal tokens, OAuth flows tied to an interactive human
user, one shared service-account key reused everywhere, comments like "my
token" / "team account".

Output: follow `prompts/_contract.md`.
