## agent_spec.md Schema

Write specs in YAML to `<target_dir>/agent_spec.md`. Fields are optional when the spec is still evolving.

```yaml
model:
  name: "datarobot/azure/gpt-5-2025-08-07" # the listing's llm_default_model, verbatim
  source: gateway                            # gateway | litellm | deployed | external
  llm_deployment_id: ""                     # only for a deployed model
  llm_base_url: ""                           # only for an external model
# Backward-compatible shorthand for a gateway model:
# model: "datarobot/azure/gpt-5-2025-08-07"
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

`model` may be a string for backward compatibility. A string is always treated as a gateway model. The preferred form is an object: `model.name` selects the model name from the listing, and `model.source` identifies whether it comes from the LLM Gateway, LiteLLM, a deployed model, or an external LLM. For a deployed model, `model.name` is the `datarobot/datarobot-deployed-llm` placeholder, which every deployment shares — `model.llm_deployment_id` identifies which one. Both fields are needed: pre-coding passes them to `setup_template.py` together, and the dress rehearsal resolves the deployment from the id.

`model.llm_base_url` identifies an external OpenAI-compatible LLM (the `external` source in the model listing), for an instance with no LLM Gateway. Set it only when `model.source` is `external`; pre-coding passes `model.name` and `model.source` to `setup_template.py`, which reads the configured URL and API key from the environment and writes the `EXTERNAL_LLM_*` keys. `model.llm_deployment_id` and `model.llm_base_url` are mutually exclusive.

When tools require external service auth, note that credentials must be configured as **runtime parameters** in the infrastructure code (see `AGENTS.md` for the pattern).

For complete working specs, see [agent-spec-examples.md](agent-spec-examples.md).
