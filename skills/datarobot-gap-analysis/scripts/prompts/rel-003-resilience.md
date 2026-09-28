# REL-003 — No error handling / retries / timeouts on external calls

Find external/network/model calls made without a timeout, without bounded
retries/backoff, and without error handling (try/except or equivalent). HTTP
calls with no `timeout=`, model calls with no retry, and unguarded I/O are the
signals.

Report the file, line, and the unprotected call.

Output: follow `prompts/_contract.md`.
