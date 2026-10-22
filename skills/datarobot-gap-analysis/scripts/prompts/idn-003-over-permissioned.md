# IDN-003 — Over-permissioned identity (relational)

Required file groups: the permissions/scope declaration (e.g. permissions.yaml,
IAM policy, OAuth scope list, manifest) AND the tool/function definitions
(e.g. tools.py). If either is absent, return `status: "skipped"`.

Compare the scopes, roles, or permissions granted to the agent against the
tools and resources it actually uses in the code. Identify any granted
permissions broader than what is used (e.g. admin, wildcard scopes, '*'
resources). Report the file, line, the granted scope, and which scopes are
unused.

Output: follow `prompts/_contract.md`. Put the granted-but-unused scope in
`evidence` and the actually-used scopes in `explanation`.
