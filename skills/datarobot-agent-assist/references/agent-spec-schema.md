## agent_spec.md Schema

Write specs in YAML to `<target_dir>/agent_spec.md`. Fields are optional when the spec is still evolving.

```yaml
model: "anthropic/claude-sonnet-4-5-20250929"   # LLM Gateway model ID, or
                                                # "datarobot/datarobot-deployed-llm"
llm_deployment_id: ""                           # only for a DataRobot-deployed LLM
system_prompt: "Your agent's instructions..."
tools:
  - function_name: tool_name
    inputs:
      - arg_name: input_arg
        type: str         # one of: str, int, float, bool, list, dict
        object_schema: "(optional: schema of dict/list contents)"
    out:
      - arg_name: output_arg
        type: str
    auth_spec:
      service_name: "External API Service"
      auth_method: api_key   # api_key | oauth2 | basic_auth | bearer_token | service_account | other
examples:
  - "Example user query 1"
  - "Example user query 2"
frontend:
  type: "chat"              # chat | multi-page | custom
  pages:
    - "Analytics - shows search history and top topics"
  requirements: "(optional additional UI requirements)"
```

`model` and `llm_deployment_id` come as a pair from [Model Selection](../SKILL.md#model-selection): a gateway model sets `model` alone, while a DataRobot-deployed LLM sets `model: "datarobot/datarobot-deployed-llm"` plus the deployment id — the model string is a shared sentinel, so the id is what identifies the LLM. Both are passed to [setup_template.py](helper-scripts.md#setup_templatepy).

When tools require external service auth, note that credentials must be configured as **runtime parameters** in the infrastructure code (see `AGENTS.md` for the pattern).

For complete working specs, see [agent-spec-examples.md](agent-spec-examples.md).
