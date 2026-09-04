# SEC-011 — Injection risk (prompt / command / deserialization / SSRF / SQL)

Identify places where untrusted input (user input, tool/function arguments,
external API responses, retrieved documents) reaches a dangerous sink without
sanitization:
- shell execution (`os.system`, `subprocess` with `shell=True`, backticks)
- `eval`/`exec`
- unsafe deserialization (`pickle.load`, `yaml.load` without `SafeLoader`)
- SQL built by string concatenation/format
- server-side requests where the URL/host comes from input (SSRF)
- LLM prompts that concatenate untrusted content into the instruction region

Report the file, line, the sink, and the untrusted source feeding it.

Output: follow `prompts/_contract.md`.
