# SEC-013 — Weak/missing encryption or disabled TLS verification

Find: plaintext transport (`http://` to non-local hosts), disabled certificate
verification (`verify=False`, `rejectUnauthorized: false`, `InsecureSkipVerify`),
weak algorithms (MD5/SHA1 for security, DES/RC4), and sensitive data persisted
without encryption.

Report the file, line, and the weakness.

Output: follow `prompts/_contract.md`.
