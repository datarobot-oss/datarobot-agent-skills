## agent_spec.md Schema

Write specs in YAML to `<target_dir>/agent_spec.md`. Fields are optional when the spec is still evolving.

```yaml
model: "datarobot/azure/gpt-5-2025-08-07"   # the listing's llm_default_model, verbatim
llm_deployment_id: ""                       # required only for a DataRobot-deployed LLM
llm_base_url: ""                            # required only for an external LLM
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

`llm_deployment_id` selects an existing DataRobot text-generation deployment instead of an LLM Gateway model. Set it only when `model` is the `datarobot-deployed-llm` placeholder, which every deployment shares — the id is what identifies which one. Both fields are needed: pre-coding passes them to `setup_template.py` together, and the dress rehearsal resolves the deployment from the id.

`llm_base_url` selects an external OpenAI-compatible LLM (the `external` source in the model listing), for an instance with no LLM Gateway. Set it only when `model` is that entry's model name; pre-coding passes both to `setup_template.py`, which reads the API key from `AGENT_ASSIST_LLM_API_KEY` and writes `USE_DATAROBOT_LLM_GATEWAY=0` with `OPENAI_API_BASE` / `OPENAI_API_KEY` (and prefixes the model `openai/`). Mutually exclusive with `llm_deployment_id`.

When tools require external service auth, note that credentials must be configured as **runtime parameters** in the infrastructure code (see `AGENTS.md` for the pattern).

For complete working specs, see [agent-spec-examples.md](agent-spec-examples.md).
