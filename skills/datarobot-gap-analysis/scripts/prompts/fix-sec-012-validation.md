# Fix SEC-012 — Add input validation at the trust boundary

Given the finding and the file, add schema/type/range validation for the
unvalidated input. Prefer the project's existing validation library (e.g.
pydantic) if present; otherwise add explicit checks that raise on invalid
input. Keep the function signature compatible.

Output: follow `prompts/_fix_contract.md`.
