# Fix IDN-003 — Narrow over-broad scopes

Given the granted scopes, the actually-used scopes (from the finding), and the
permissions/scope declaration file, rewrite the declaration to grant only the
scopes the code actually exercises. Remove wildcards and admin/broad scopes
that are unused. Preserve file format (YAML/JSON/etc.).

Output: follow `prompts/_fix_contract.md`. List removed scopes in `explanation`.
