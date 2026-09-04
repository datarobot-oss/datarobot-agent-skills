# Fix REL-003 — Add timeouts, retries, error handling

Given the finding and the file, add a `timeout=` to the external call, wrap it
with bounded retry/backoff (use the project's existing retry util like
`tenacity` if present, else a small loop), and add error handling. Keep the
call's return contract unchanged.

Output: follow `prompts/_fix_contract.md`.
