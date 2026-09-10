# SEC-012 — Missing input validation on tool inputs & external data

Find tool/function entry points and external-data consumers that use their
inputs without type/range/schema validation. Look for tool functions that
accept raw `str`/`dict`/`Any` and pass them straight into side-effecting logic,
and external API responses consumed without checking shape/status.

Report the file, line, and the unvalidated input. Judge each entry point once:
a module whose tools all follow the same pattern (typed parameters validated by
the framework, or raw dicts passed straight through) is a single finding with
the module named, not one finding per tool or per parameter. A tool whose
parameters are typed and validated by its framework (pydantic models,
`Annotated` types on an MCP or LangChain tool) is not a finding on its own;
report it only where a value inside a typed container (a `dict[str, Any]`
field, a free-form string) reaches a side effect unchecked.

Output: follow `prompts/_contract.md`.
