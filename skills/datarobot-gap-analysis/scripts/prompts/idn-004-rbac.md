# IDN-004 — No least-privilege boundary / missing RBAC on actions

Find high-impact or privileged operations (delete, write to prod, admin APIs,
financial actions, user-data access) that execute without any role/permission
check or authorization boundary. Look for missing authz gates between a caller
and a privileged operation.

Report the file, line, and the unguarded privileged action.

Output: follow `prompts/_contract.md`.
