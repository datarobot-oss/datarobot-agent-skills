# Fix AIG-006 — Add cost/token controls

Given the finding and the file, add a `max_tokens` cap to the model call and,
where applicable, a simple bound on iterations/requests. Keep behavior
otherwise unchanged. If a rate limiter is non-trivial, add the token cap and
note rate-limiting as `manual_followup`.

Output: follow `prompts/_fix_contract.md`.
