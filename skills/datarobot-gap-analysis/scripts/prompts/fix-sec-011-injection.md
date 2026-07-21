# Fix SEC-011 — Close injection vector

Given the finding and the file, apply the minimal safe fix for the specific
sink:
- shell: drop `shell=True`, pass an argument list, or use a safe API
- eval/exec: replace with a safe parser / explicit dispatch
- deserialization: use `yaml.safe_load` / a safe format instead of pickle
- SQL: use parameterized queries
- SSRF: validate/allowlist the host
- prompt injection: separate untrusted content from instructions / add delimiters + validation

Output: follow `prompts/_fix_contract.md`. If the safe fix needs broad
redesign, return `can_fix: false`.
