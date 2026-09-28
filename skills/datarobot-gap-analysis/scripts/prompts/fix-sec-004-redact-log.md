# Fix SEC-004 — Redact secret from log/print statement

Given the finding and the file, modify the logging/print/trace call so the
credential is not emitted. Replace the secret-bearing value with a redacted
placeholder (e.g. `***redacted***` or a masked last-4) or remove the secret
argument entirely while keeping the log message useful. Do not change unrelated
logging.

Output: follow `prompts/_fix_contract.md`.
