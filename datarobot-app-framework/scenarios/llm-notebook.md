---
name: llm-notebook
intent: [LLM notebook, notebook with LLM, iterate with LLM, LLM in Jupyter, fast LLM prototype, notebook deployment, no agent]
tier: core
components:
  - af-component-base
  - af-component-llm
output: Deployed LLM custom model + notebook (local or DataRobot)
---

> **Note:** Complete prerequisites first — see SKILL.md.

## Step 1 — Create recipe directory

```bash
mkdir recipe-my-llm && cd recipe-my-llm
```

## Step 2 — Scaffold base

```bash
uvx copier copy https://github.com/datarobot/af-component-base .
```

## Step 3 — Add LLM

```bash
uvx copier copy https://github.com/datarobot-community/af-component-llm .
```

Key prompts:
- **LLM folder name**: `llm` (default)
- **Model name**: `azure-openai-gpt-4o-mini` or as required
- **Base answers file**: `.datarobot/answers/base.yml`

## Step 4 — Configure environment

```bash
dr dotenv setup
```

Key prompts:
- **Pulumi passphrase**: any value
- **Use case**: can leave blank
- **LLM Gateway config**: select LLM Gateway with External Model

Press enter to accept defaults for most prompts.

## Step 5 — Deploy LLM

```bash
dr task deploy
```

Creates a stack, previews resources, deploys. Note the deployment ID in the output.

Check anytime:

```bash
dr task infra:info
```

## Step 6 — Set up notebook

```bash
mkdir notebooks && cd notebooks
uv init .
uv add jupyter dotenv litellm
uv run jupyter notebook
```

> If running in GitHub Codespaces: skip `uv` commands, run `pip install dotenv litellm` instead, then use the "Create Notebook" button.

Create a new notebook and add these cells:

```python
from dotenv import load_dotenv
from litellm import completion
from os import getenv
from urllib.parse import urljoin

load_dotenv()

DATAROBOT_API_TOKEN = getenv('DATAROBOT_API_TOKEN')
DATAROBOT_ENDPOINT = getenv('DATAROBOT_ENDPOINT')
```

```python
# From `dr task infra:info`
LLM_DEPLOYMENT_ID = '<DEPLOYMENT_ID>'
LLM_DEFAULT_MODEL = 'datarobot/azure/gpt-5-mini-2025-08-07'
DEPLOYMENT_BASE = urljoin(DATAROBOT_ENDPOINT, f'v2/deployments/{LLM_DEPLOYMENT_ID}/chat/completions')

def ask_llm(*messages):
    return completion(
        base_url=DEPLOYMENT_BASE,
        api_key=DATAROBOT_API_TOKEN,
        model=LLM_DEFAULT_MODEL,
        messages=messages
    )
```

```python
response = ask_llm({"content": "Hi", "role": "user"})
response.choices[0].message.content
```

## Deploy notebook to DataRobot (optional)

Create `infra/infra/notebook.py`:

```python
from pathlib import Path
from pulumi_datarobot.notebook import Notebook
from . import use_case

PROJECT_ROOT = Path(__file__).resolve().parents[2].absolute()
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "llm_example.ipynb"
notebook = Notebook("llm_example_notebook", file_path=str(NOTEBOOK_PATH), use_case_id=use_case.id)
```

Then deploy:

```bash
dr task deploy
```

In the DataRobot notebook, install dependencies once via terminal:

```bash
pip install litellm dotenv
```

## Tear down

```bash
dr task infra:down
```
