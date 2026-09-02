## LLM Selection

`list_llm_models.py` returns four kinds of entry, told apart by `source`:

- `gateway` — a model in the DataRobot LLM Gateway catalog. Selected by its `llm_default_model`.
- `litellm` — a model exposed by LiteLLM through `dr llm-gateway list`. Selected by its `llm_default_model`.
- `deployed` — an existing DataRobot text-generation deployment. Selected by its `deployment_id`.
- `external` — an OpenAI-compatible model configured through the `AGENT_ASSIST_LLM_*` environment, for an instance with no LLM Gateway. Selected by its `llm_default_model` (the raw model name) together with its `base_url`.

**Copy `llm_default_model` verbatim.** It is the only field that goes into `agent_spec.md` and `.env`. A `gateway` entry also carries an `id` (the catalog's `llmId`, e.g. `azure-openai-gpt-5`) and an `api_model` (e.g. `azure/gpt-5-2025-08-07`); neither works as a model name. The gateway rejects the `id` outright, and `api_model` is missing the `datarobot/` prefix that routes the request to DataRobot rather than straight to the provider. `setup_template.py` refuses an `id` rather than letting it reach `.env`. On a `deployed` entry, `id` is the deployment id instead, and it is what you want: see below.

### Recommending

- Prefer a `gpt-5`, `claude-4-5`, or `gemini-2.5` gateway model unless the user gives cost or other constraints.
- If none of those families appear, take the highest-capability gateway model by name: prefer `large`, `pro`, `opus`, `sonnet` over `mini`, `haiku`, `flash`.
- **If there is no `gateway` entry at all**, the LLM Gateway is disabled or empty on this instance. That is the normal shape of an on-prem install, not an error. Recommend a `deployed` entry, or the `external` entry when one is configured, name it by its `name`, and tell the user that is what you are doing and why.
- Only show the full catalog when the user explicitly asks to browse.

### Recording a deployed LLM in `agent_spec.md`

Every deployment reports the same `llm_default_model`, the placeholder `datarobot/datarobot-deployed-llm`. It identifies the *source*, never one deployment. So a deployed choice is a pair, and both fields are required:

```yaml
model:
	name: "datarobot/datarobot-deployed-llm"
	source: deployed
	llm_deployment_id: "6a43eb5f10dbecadbebc5b2b"
```

Take `model.llm_deployment_id` from the entry's `deployment_id`. Without it nothing downstream can tell which deployment was chosen: `setup_template.py` refuses the pair outright, and the dress rehearsal would have to guess.

A gateway choice sets `model.name` and `model.source: gateway`; it does not need either optional model field.

### Recording an external LLM in `agent_spec.md`

An `external` entry appears only when `AGENT_ASSIST_LLM_MODEL_NAME`, `AGENT_ASSIST_LLM_BASE_URL`, and `AGENT_ASSIST_LLM_API_KEY` are all set. It is a pair too: `model.name` is the entry's `llm_default_model` (the raw model name, no `datarobot/` prefix) and `model.llm_base_url` is its `base_url`.

```yaml
model:
	name: "local-ollama"
	source: external
	llm_base_url: "http://localhost:4000/v1"
```

Both are required at setup: `setup_template.py` recognizes the choice as external only when `model.name` **and** `model.llm_base_url` match the environment exactly, otherwise it treats the value as a gateway model and fails. The API key is never written to the spec; it stays in the environment and the script reads it there. An external LLM cannot be combined with `model.llm_deployment_id`, and it is not wired into the dress rehearsal.

### What the choice changes downstream

| Step | Gateway model | LiteLLM model | Deployed LLM | External LLM |
|---|---|---|---|---|
| [Template setup](helper-scripts.md#setup_templatepy) | `--llm-model` **and** `--llm-source gateway` | `--llm-model` **and** `--llm-source litellm` | `--llm-model`, `--llm-source deployed`, and `--llm-deployment-id` | `--llm-model` **and** `--llm-source external` |
| `.env` written | `LLM_DEFAULT_MODEL` | `EXTERNAL_LLM_MODEL`, `EXTERNAL_LLM_API_KEY`, `EXTERNAL_LLM_BASE_URL` | plus `LLM_DEPLOYMENT_ID`, `INFRA_ENABLE_LLM=deployed_llm.py`, `USE_DATAROBOT_LLM_GATEWAY=0` | `EXTERNAL_LLM_MODEL`, `EXTERNAL_LLM_API_KEY`, `EXTERNAL_LLM_BASE_URL` |
| [Dress rehearsal](dress-rehearsal.md) | LLM Gateway chat endpoint | LiteLLM chat endpoint | the deployment's own chat endpoint | not supported yet |

On the deployed path the deployment id is the only thing that selects the model. `dr dotenv setup` rebuilds `.env` from the template's own prompt schema, which does not carry `LLM_DEFAULT_MODEL` for that path, so a real model name passed alongside an id is not persisted. Routing is unaffected.

### Caveats worth telling the user

- A deployment is offered when it is active and its target type is text generation. Nothing checks that it answers chat requests, and some text-generation deployments (guard models, for instance) do not. If the rehearsal reports the deployment as unavailable, that is the likely cause.
- Deployed entries carry no provider or context window, so those columns read `-`.
- The `Deployment ID` column appears in the table only when a deployed entry is present.
- Deployed entries require `dr` v0.2.79 or newer to appear in the CLI listing. On an older `dr` the script falls back to a direct API call, so they still list.
