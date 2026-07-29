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

### list_llm_models.py

Lists the LLMs available for the agent's `model` field. Delegates to `dr llm-gateway list --output-format json`, so the skill and the CLI never disagree about what is available — which makes the [DataRobot CLI](dr-cli-setup.md) a hard requirement of model selection, not just of deployment.

```bash
python <skill_scripts_dir>/list_llm_models.py \
  --json \
  --target-dir <target_dir>
```

`<target_dir>/.env` credentials are passed through to the CLI. When they are absent or stale the CLI falls back to its own authenticated profile, so verify `dr auth check` if the listing looks like the wrong DataRobot instance.

### clone_template.py

Clones the DataRobot agent application template repository (URL and tag are defined in the script):

```bash
python <skill_scripts_dir>/clone_template.py \
  --target-dir <target_dir>
```

### setup_template.py

Sets up a template repository for initializing a new agent project:

```bash
python <skill_scripts_dir>/setup_template.py \
  --llm-model <model-name> \
  --target-dir <target_dir>
```

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
