# SEC-001 — Secret reachable by the LLM context (relational)

Required file groups: the file(s) where the credential is READ (e.g. config.py,
auth.py) AND the file(s) where the prompt/system-message/tool-description is
BUILT (e.g. agent.py, prompt templates). If either group is absent, return
`status: "skipped"`.

Trace whether any credential value (API key, token, password) flows into a
prompt, system message, or tool description that reaches the model at inference
time. Identify where the credential is read and whether it ends up in
model-visible text. Report the file, line, and the code path connecting them.
Do not include the actual secret value.

Output: follow `prompts/_contract.md`.
