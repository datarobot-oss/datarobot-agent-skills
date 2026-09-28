# Fix SEC-013 — Restore encryption / TLS verification

Given the finding and the file: re-enable certificate verification (remove
`verify=False` / `rejectUnauthorized: false`), switch `http://` to `https://`
for non-local hosts, and replace weak algorithms with strong ones (e.g.
SHA-256, AES-GCM). Make the minimal change.

Output: follow `prompts/_fix_contract.md`.
