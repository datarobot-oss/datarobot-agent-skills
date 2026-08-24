## Helper Scripts

Scripts live in `<skill_scripts_dir>` (`scripts/` next to `SKILL.md`). Resolve the path once per session — see [Script Path Resolution](../SKILL.md#script-path-resolution).

The canonical template URL is the `REPO_URL` constant in `clone_template.py` — use it for remote comparison; do not hardcode the URL elsewhere.

### `.env` file

Project `.env` belongs at `<target_dir>/.env` only. Scripts that read or create it require `--target-dir <target_dir>`:

| Script | When |
|--------|------|
| `list_llm_models.py` | Design — model selection |
| `rehearsal.py` | Design — dress rehearsal (`--init` and optional turn override) |
| `setup_template.py` | Pre-coding — template setup (step 9) |

Do not run `dr dotenv setup` manually in cwd when designing in a subdirectory.

### clone_template.py

Clones the DataRobot agent application template repository (URL and tag are defined in the script):

```bash
python <skill_scripts_dir>/clone_template.py \
  --target-dir <target_dir>
```

### list_llm_models.py

Lists the LLMs available on the instance the project's `.env` points at, from two sources: the LLM Gateway catalog (`source: gateway`) and existing DataRobot text-generation deployments (`source: deployed`). Sourced from `dr llm-gateway list`, with a direct REST call as fallback.

```bash
python <skill_scripts_dir>/list_llm_models.py \
  --json \
  --target-dir <target_dir>
```

Pass a `gateway` entry's `llm_default_model` to `setup_template.py --llm-model`. That is the only field that works as a model name: `id` is the catalog's `llmId`, which the gateway rejects, and `api_model` lacks the `datarobot/` prefix that routes the call to DataRobot.

Every `deployed` entry reports the same `llm_default_model` placeholder, so `deployment_id` is what identifies one; `name` is its deployment label.

If the listing looks like it came from the wrong DataRobot instance, compare the `listing requested from` line against the host named in the CLI log lines that follow it. The CLI honors the credentials passed to it only once they verify, and otherwise falls back to its stored profile, so a stale project `.env` yields another instance's catalog rather than an error.

### setup_template.py

Sets up a template repository for initializing a new agent project:

```bash
python <skill_scripts_dir>/setup_template.py \
  --llm-model <model-name> \
  --target-dir <target_dir>
```

For a DataRobot-deployed LLM, pass the spec's `llm_deployment_id` as well:

```bash
python <skill_scripts_dir>/setup_template.py \
  --llm-model <model-name> \
  --llm-deployment-id <deployment-id> \
  --target-dir <target_dir>
```

That writes `LLM_DEPLOYMENT_ID`, `INFRA_ENABLE_LLM=deployed_llm.py`, and `USE_DATAROBOT_LLM_GATEWAY=0` into `.env`, which is what makes the template route to the deployment. Passing the `datarobot-deployed-llm` placeholder as `--llm-model` **without** an id is refused: the template would stay on its gateway configuration and fail much later at `pulumi up` with `Model 'datarobot-deployed-llm' not found in catalog`.

On the deployed path the deployment id is the only thing that selects the model. `dr dotenv setup` rebuilds `.env` from the template's `.datarobot/cli/llm.yml`, whose deployed-LLM group does not include `LLM_DEFAULT_MODEL`, so that key is dropped and the template falls back to its own `datarobot/datarobot-deployed-llm` placeholder. Routing is unaffected; a real model name passed as `--llm-model` alongside an id does not survive.

### select_framework.py

Saves the chosen agentic framework to `.datarobot/answers/agent-agent.yml` (`agent_template_framework`). Preserves all other fields in the file.

```bash
python <skill_scripts_dir>/select_framework.py \
  --framework <value> \
  --target-dir <target_dir>
```

Valid `--framework` values: `langgraph`, `crewai`, `llamaindex`, `nat`, `base`

### check_codespace.py

Used in the Pre-requisite Check (no-op outside a DataRobot Codespace):

```bash
python <skill_scripts_dir>/check_codespace.py
```

### rehearsal.py

Dress rehearsal engine — see [dress-rehearsal.md](dress-rehearsal.md).
