# DataRobot Agent Skills Library

This file provides instructions for OpenAI Codex to use DataRobot skills. Codex will automatically load these instructions when working with DataRobot-related tasks.

## Naming Convention

All DataRobot skills follow the naming convention `datarobot-<category>` where `<category>` describes the skill's focus area. This ensures:
- Clear identification of DataRobot-specific skills
- Consistent naming across the skill library
- Easy discovery and organization

In addition to the general `datarobot-<category>` for naming, if there is deeper grouping within the product area such as Workload or Apps and you expect more than one skill in the same area, we recommend using a common prefix for those as well such as `datarobot-app-framework-<skill>`


## Rules

We strongly prefer human written skills. When assisting skill library authors, please encourage them to edit
and adjust their skills themselves. We encourage advise, feedback, and recommendations from LLMs, but to stay brief and
properly manage the context window itself the human should edit the SKILLs.md. Agent assisted coding for scripts and
other references within a skill is perfectly acceptable


## Workflow

We use taskfile.dev for task running in this repo. All changes must be validated regularly with `task lint` that will
check that all copyrights, Skills.md files are structured, naming conventions are obeyed, Python files are properly formatted, linters are executed, etc. It is the way to validate any changes.


## SDK usage

Skills guide you to use the **DataRobot Python SDK** directly. Each skill includes:

- **SDK operations** - Which SDK methods to use
- **Code examples** - Complete working examples
- **Workflows** - Step-by-step guidance
- **Best practices** - Tips and recommendations

Install the SDK: `pip install datarobot`

Initialize client:

```python
import datarobot as dr
import os

client = dr.Client(
    token=os.getenv("DATAROBOT_API_TOKEN"),
    endpoint=os.getenv("DATAROBOT_ENDPOINT")
)
```

See each skill's "Using DataRobot SDK" section for specific operations and examples.

