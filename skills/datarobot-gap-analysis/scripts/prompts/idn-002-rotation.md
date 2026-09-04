# IDN-002 — No credential rotation / no token expiry

Determine whether credentials are static and long-lived with no rotation or
refresh mechanism. Look for: tokens loaded once and never refreshed, absence of
expiry handling, no use of short-lived/STS-style credentials, comments
indicating manual rotation.

Report the file, line, and the static credential pattern.

Output: follow `prompts/_contract.md`.
