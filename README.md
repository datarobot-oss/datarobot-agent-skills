# DataRobot Skills

DataRobot Skills are Agent Context Protocol (ACP) definitions for AI/ML tasks like model training, deployment, predictions, feature engineering, and model monitoring. They are interoperable with all major coding agent tools like OpenAI Codex, Anthropic's Claude Code, Google DeepMind's Gemini CLI, Cursor, and VS Code Copilot.

## Quick Start

Install skills to **all** your AI agents with one command using the [universal skills installer](https://github.com/skillcreatorai/Ai-Agent-Skills):

```bash
# Install this entire skill library to all agents at once
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills

# Or install a specific skill
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills/datarobot-predictions

# Install to a specific agent only
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills --agent cursor
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills --agent claude
```

**Supported agents:** Claude Code, Cursor, Codex, Amp, VS Code Copilot (GitHub Copilot), Gemini CLI, Goose, Letta, Kilo Code, and OpenCode.

By default, the installer copies skills to all supported agents simultaneously. No configuration needed!

For agent-specific installation methods, see the [Installation](#installation) section below.

## How do Skills work?

In practice, skills are self-contained folders that package instructions, scripts, and resources together for an AI agent to use on a specific use case. Each folder includes a `SKILL.md` file with YAML frontmatter (name and description) followed by the guidance your coding agent follows while the skill is active.

> **Note**: 'Skills' is actually an Anthropic term used within Claude AI and Claude Code and not adopted by other agent tools, but we love it! OpenAI Codex uses an `AGENTS.md` file to define the instructions for your coding agent. Google Gemini uses 'extensions' to define the instructions for your coding agent in a `gemini-extension.json` file. This repo is compatible with all of them, and more!

## Naming Convention

All DataRobot skills follow the naming convention `datarobot-<category>` where `<category>` describes the skill's focus area. This ensures:
- Clear identification of DataRobot-specific skills
- Consistent naming across the skill library
- Easy discovery and organization

## Installation

DataRobot skills are compatible with Claude Code, Codex, Gemini CLI, Cursor, and VS Code Copilot. Integrations with Windsurf and Continue are on the way.

### Claude Code

Register the repository as a plugin marketplace:
```
/plugin marketplace add datarobot-oss/datarobot-agent-skills
```

To install a skill, run:
```
/plugin install <skill-folder>@datarobot-skills
```

For example:
```
/plugin install datarobot-model-training@datarobot-skills
```

### Codex

Codex will identify the skills via the `AGENTS.md` file. You can verify the instructions are loaded with:
```
codex --ask-for-approval never "Summarize the current instructions."
```

For more details, see the Codex AGENTS guide.

### Gemini CLI

This repo includes `gemini-extension.json` to integrate with the Gemini CLI.

Install locally:
```bash
gemini extensions install . --consent
```

or use the GitHub URL:
```bash
gemini extensions install https://github.com/datarobot-oss/datarobot-agent-skills.git --consent
```

See Gemini CLI extensions docs for more help.

### Cursor

Cursor can automatically detect and use skills from this repository. There are two main approaches:

**Option 1: Use AGENTS.md (Recommended)**

Cursor will automatically read the `AGENTS.md` file when you open this repository as your workspace. The skills are available immediately without additional configuration.

To verify skills are loaded:
1. Open Cursor in this repository directory
2. Open the AI chat panel (Cmd/Ctrl + L)
3. Ask: "What DataRobot skills are available?"

**Option 2: Use .cursorrules**

You can also reference specific skills in your `.cursorrules` file to ensure they're always loaded:

```
# .cursorrules
You have access to DataRobot skills in this repository.

Available skills (in datarobot-* folders):
- datarobot-model-training: Model training and project creation
- datarobot-predictions: Making predictions and generating templates
- datarobot-model-deployment: Deploying and managing models
- datarobot-feature-engineering: Feature analysis and engineering
- datarobot-model-monitoring: Model performance monitoring
- datarobot-model-explainability: Model explainability and diagnostics
- datarobot-data-preparation: Data upload and validation

When asked to use a DataRobot skill, read the corresponding SKILL.md file for detailed guidance.
```

**Using skills in Cursor:**
- "Use the datarobot-predictions skill to generate a template for deployment abc123"
- "Follow the datarobot-model-training skill to create a new project"
- "Check the datarobot-model-monitoring skill to analyze data drift"

### VS Code Copilot (GitHub Copilot)

VS Code with GitHub Copilot can automatically detect and use skills from this repository through the `AGENTS.md` file.

**Setup:**

1. Open this repository in VS Code
2. Ensure you have the GitHub Copilot extension installed and activated
3. Skills are automatically available through the `AGENTS.md` file

**Verifying skills are loaded:**

Open Copilot Chat (Cmd/Ctrl + I) and ask:
- "What DataRobot skills are available?"
- "List the available skills in this repository"

**Using skills in VS Code Copilot:**

In Copilot Chat, reference skills naturally:
- "Use the datarobot-predictions skill to generate a template for deployment abc123"
- "Following the datarobot-model-training skill, create a new project for customer churn prediction"
- "Check the datarobot-model-monitoring skill and help me analyze data drift"

**Pro tip:** You can also use the `@workspace` agent in Copilot Chat to ensure it has full context of the repository and available skills.

## Skills

This repository contains skills for common DataRobot workflows. You can also contribute your own skills to the repository.

### Available skills

| Skill Folder | Description | Documentation |
|-------------|-------------|--------------|
| `datarobot-model-training/` | Instructions and utilities for training models, managing projects, and running AutoML experiments. | [SKILL.md](datarobot-model-training/SKILL.md) |
| `datarobot-model-deployment/` | Tools for deploying models, managing deployments, and configuring prediction environments. | [SKILL.md](datarobot-model-deployment/SKILL.md) |
| `datarobot-predictions/` | Guidance for making predictions, batch scoring, real-time predictions, and generating prediction datasets. | [SKILL.md](datarobot-predictions/SKILL.md) |
| `datarobot-feature-engineering/` | Instructions for feature engineering, feature discovery, and feature importance analysis. | [SKILL.md](datarobot-feature-engineering/SKILL.md) |
| `datarobot-model-monitoring/` | Tools for monitoring model performance, tracking data drift, and managing model health. | [SKILL.md](datarobot-model-monitoring/SKILL.md) |
| `datarobot-model-explainability/` | Tools for model explainability, prediction explanations, SHAP values, and model diagnostics. | [SKILL.md](datarobot-model-explainability/SKILL.md) |
| `datarobot-data-preparation/` | Utilities for data upload, dataset management, and data validation. | [SKILL.md](datarobot-data-preparation/SKILL.md) |

## Using skills in your coding agent

Once a skill is installed, mention it directly while giving your coding agent instructions:

- "Use the DataRobot model training skill to create a new project and start AutoML training."
- "Use the DataRobot predictions skill to generate a prediction dataset template for deployment abc123."
- "Use the DataRobot feature engineering skill to analyze feature importance for my model."
- "Use the DataRobot model monitoring skill to check data drift for deployment xyz789."

Your coding agent automatically loads the corresponding `SKILL.md` instructions and helper scripts while it completes the task.

### Helper Scripts

Some skills include executable helper scripts that Claude can run directly:

- **datarobot-predictions**: `get_deployment_features.py`, `generate_prediction_data_template.py`, `validate_prediction_data.py`, `make_prediction.py`
- **datarobot-model-training**: `create_project.py`, `start_training.py`, `list_models.py`
- **datarobot-data-preparation**: `upload_dataset.py`

These scripts are located in each skill's `scripts/` directory and can be executed directly or used as reference when writing code.

## Contribute or customize a skill

1. Copy one of the existing skill folders (for example, `datarobot-model-training/`) and rename it.
2. Update the new folder's `SKILL.md` frontmatter:
   ```yaml
   ---
   name: datarobot-my-skill-name
   description: Describe what the skill does and when to use it
   ---
   
   # Skill Title
   Guidance + examples + guardrails
   ```
3. **Important**: Follow the naming convention `datarobot-<category>` for all skill names and folder names.
4. Add or edit supporting scripts, templates, and documents referenced by your instructions.
5. Reinstall or reload the skill bundle in your coding agent so the updated folder is available.

## Development & Validation

This repository includes automated validation and linting tools to ensure consistency and quality across all skills.

### Prerequisites

- [Task](https://taskfile.dev/) - Task runner (install: `brew install go-task` or `sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d`)
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Available Tasks

Run `task --list` to see all available tasks:

```bash
# Validate all skills (naming convention, structure, frontmatter)
task validate

# Lint all Python scripts with ruff
task ruff:check

# Format all Python scripts with ruff
task format

# Run all checks (validate + lint + format check)
task lint

# Default task (runs lint)
task
```

### Validation Rules

The `bin/validate_skills.py` script enforces:

1. **Naming Convention**: All skill folders must start with `datarobot-`
2. **Structure**: Each skill must have a `SKILL.md` file
3. **Frontmatter**: The `name` field in SKILL.md must match the folder name

Example:
```
datarobot-my-skill/
  └── SKILL.md
      ---
      name: datarobot-my-skill  # Must match folder name
      description: ...
      ---
```

### Continuous Integration

This repository uses GitHub Actions for automated checks:

- **[Validate Skills](.github/workflows/validate-skills.yml)** - Validates skill naming and structure on every push/PR
- **[Trivy Security Scan](.github/workflows/trivy-scan.yml)** - Scans for secrets and security issues daily and on every push/PR

All checks must pass before merging pull requests.

## How Skills Work

Skills guide your coding agent to use the **DataRobot Python SDK** directly. The agent will:

1. Install the `datarobot` Python package if needed
2. Use the SDK based on skill instructions and examples
3. Write and execute Python code to interact with DataRobot

**Example**: When you ask "Generate a prediction dataset template", the agent reads `datarobot-predictions/SKILL.md`, then writes Python code using `datarobot` SDK to get deployment features and generate the template.

### Optional: MCP Server Support

If you have a DataRobot MCP server running, agents can also use MCP tools as an alternative to direct SDK usage. See the [MCP Server Template](https://github.com/datarobot-community/datarobot-mcp-template) for more information.

## Prerequisites

To use DataRobot skills, you need:

- **DataRobot account** with API access
- **DataRobot API token** and endpoint
- **Python environment** where your coding agent can install packages

The agent will automatically install the `datarobot` Python package when needed.

## Additional Documentation

- [Usage Guide](docs/USAGE_GUIDE.md) - Complete guide on how to use DataRobot skills
- [LangGraph Integration](docs/LANGGRAPH_INTEGRATION.md) - How to use skills with LangGraph agents
- [Agent Framework Integration](docs/AGENT_FRAMEWORK_INTEGRATION.md) - Patterns for LangGraph, PydanticAI, and other programmatic agent frameworks

## Additional references

- Browse the latest instructions, scripts, and templates directly at [datarobot-oss/datarobot-agent-skills](https://github.com/datarobot-oss/datarobot-agent-skills).
- Review [DataRobot documentation](https://docs.datarobot.com/) for the specific libraries or workflows you reference inside each skill.
- Check out the [DataRobot Python SDK Documentation](https://datarobot-public-api-client.readthedocs-hosted.com/) for API reference

