# Migration Spec Output Contract

The extraction prompt receives the target agent's key files and MUST return a single
JSON object describing the business logic to carry over. The migration engine renders
this as an `agent_spec.md` for human review and assembles a carryover bundle.

```json
{
  "name": "short-agent-name",
  "description": "one sentence: what this agent does",
  "framework": "langgraph | crewai | llamaindex | custom | unknown",
  "model": "provider/model-id as found, or '' if not pinned",
  "system_prompt": "the effective system/instruction prompt text",
  "tools": [
    {
      "name": "tool_function_name",
      "description": "what it does",
      "inputs": [{ "name": "arg", "type": "str" }],
      "outputs": [{ "name": "result", "type": "dict" }],
      "auth": "service + auth method, or '' if none",
      "source_file": "relative/path.py"
    }
  ],
  "workflow": "prose describing the graph/control flow, branches, and any human-in-the-loop steps",
  "domain_dependencies": ["package-name"],
  "carryover_files": ["relative/path.py", "relative/prompts/system.md"],
  "manual_wiring": ["anything ambiguous or that a human must reconnect after scaffolding"],
  "confidence": "high | medium | low"
}
```

Rules:
- `system_prompt` is the reconstructed effective text, never a secret value.
- `tools` lists only real domain tools found in the code (not framework helpers).
- `carryover_files` are repo-relative paths that hold logic to lift verbatim.
- `domain_dependencies` excludes replaceable framework/SDK plumbing.
- If the repo is not actually an agent, return `framework: "unknown"`, empty `tools`,
  and explain in `manual_wiring`.
