# DataRobot skills

## Overview

Agentic skills are modular, task-specific capability packages that help an AI agent move from general reasoning to reliable execution. Each skill bundles instructions, examples, and supporting resources so that the agent can load only what it needs for the current task, reducing context overload and improving tool use within a given workflow.

DataRobot Skills are Agent Context Protocol (ACP) definitions for AI/ML tasks such as model training, deployment, predictions, feature engineering, and model monitoring. They work with major coding agents, including OpenAI Codex, Anthropic Claude Code, Google Gemini CLI, Cursor, and VS Code Copilot.

> [!NOTE]
> "Skills" is an Anthropic term used in Claude AI and Claude Code, but the concept applies more broadly. OpenAI Codex uses `AGENTS.md` to define agent instructions, and Gemini uses `gemini-extension.json` for extensions. This repository is compatible with all of them, and more.

## Quick start

> [!NOTE]
> Supported agents for DataRobot skills include: Claude Code, Cursor, Codex, Amp, VS Code Copilot (GitHub Copilot), Gemini CLI, Goose, Letta, Kilo Code, and OpenCode.

Install all DataRobot skills or just specific skillsfor **all** your AI agents with one command by using the [universal skills installer](https://github.com/skillcreatorai/Ai-Agent-Skills).

**For all skills:**

```bash
# Install this entire skill library to all agents at once
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills
```

**For a specific skill:**

```bash
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills/datarobot-predictions
```

**For a specific agent:**

```bash
# Install to a specific agent only
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills --agent cursor
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills --agent claude
```

> [!NOTE]
> By default, the installer copies skills to all supported agents at the same time. No configuration is required.
> For agent-specific installation methods, see the [Installation](#installation) section below.

## How do skills work?

Skills are self-contained folders that package instructions, scripts, and resources for a specific use case. Each folder includes a `SKILL.md` file with YAML frontmatter (`name` and `description`), followed by the guidance your coding agent uses while the skill is active.

> [!NOTE]
> All DataRobot skills follow the naming convention `datarobot-<category>`, where `<category>` describes the skill's focus area. This provides clear identification of DataRobot-specific skills, consistent naming across the skill library, and easy discovery and organization.

## Installation to your coding agent

DataRobot skills are compatible with Claude Code, Codex, Gemini CLI, Cursor, and VS Code Copilot. Support for Windsurf and Continue is planned.
Click on the section that corresponds to your coding agent to see the installation instructions.

<details><summary><strong>Claude Code</strong></summary>

Register the repository as a plugin marketplace:

```bash
/plugin marketplace add datarobot-oss/datarobot-agent-skills
```

To install a skill, run:

```bash
/plugin install <skill-folder>@datarobot-skills
```

For example:

```bash
/plugin install datarobot-model-training@datarobot-skills
```

</details>

<details><summary><strong>Codex</strong></summary>

Codex identifies the skills through the `AGENTS.md` file. You can verify that the instructions are loaded by running:

```bash
codex --ask-for-approval never "Summarize the current instructions."
```

For more details, see the Codex `AGENTS.md` documentation. <!-- Hyperlink?? -->

</details>

<details><summary><strong>Gemini CLI</strong></summary>

This repository includes `gemini-extension.json` for Gemini CLI integration.

Install locally:

```bash
gemini extensions install . --consent
```

Or install from the GitHub URL:

```bash
gemini extensions install https://github.com/datarobot-oss/datarobot-agent-skills.git --consent
```

See the Gemini CLI extensions documentation for more information. <!-- Hyperlink?? -->

</details>

<details><summary><strong>Cursor</strong></summary>

Cursor can automatically detect and use skills from this repository in two main ways:

**Option 1: Use `AGENTS.md`**

>[!NOTE]
> This option is the recommended approach.

When you open this repository as your workspace, Cursor automatically reads the `AGENTS.md` file. The skills are available immediately without additional configuration.

To verify that the skills are loaded:

1. Open Cursor in this repository.
2. Open the AI chat panel (`Cmd/Ctrl + L`).
3. Ask: "What DataRobot skills are available?"

**Option 2: Use `.cursorrules`** <!-- Why offer this if the above is recommended? -->

You can also reference specific skills in your `.cursorrules` file to make sure they are always loaded:

```text
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

</details>

<details><summary><strong>VS Code Copilot (GitHub Copilot)</strong></summary>

VS Code with GitHub Copilot can automatically detect and use skills from this repository through the `AGENTS.md` file.

**Setup:**

1. Open this repository in VS Code.
2. Ensure that the GitHub Copilot extension is installed and activated.
3. Skills are automatically available through the `AGENTS.md` file.

**Verify that the skills are loaded:**

Open Copilot Chat (`Cmd/Ctrl + I`) and ask:

- "What DataRobot skills are available?"
- "List the available skills in this repository"

**Using skills in VS Code Copilot:**

In Copilot Chat, reference skills naturally:

- "Use the datarobot-predictions skill to generate a template for deployment abc123"
- "Following the datarobot-model-training skill, create a new project for customer churn prediction"
- "Check the datarobot-model-monitoring skill and help me analyze data drift"

>[!TIP]
> You can also use the `@workspace` agent in Copilot Chat to give it full context about the repository and available skills.

</details>

## Skills

This repository contains skills for common DataRobot workflows. You can also contribute your own skills.

### Available skills

| Skill Folder | Description | Documentation |
| ------------ | ----------- | ------------- |
| `skills/datarobot-model-training/` | Instructions and utilities for training models, managing projects, and running AutoML experiments. | [SKILL.md](skills/datarobot-model-training/SKILL.md) |
| `skills/datarobot-model-deployment/` | Tools for deploying models, managing deployments, and configuring prediction environments. | [SKILL.md](skills/datarobot-model-deployment/SKILL.md) |
| `skills/datarobot-predictions/` | Guidance for making predictions, batch scoring, real-time predictions, and generating prediction datasets. | [SKILL.md](skills/datarobot-predictions/SKILL.md) |
| `skills/datarobot-feature-engineering/` | Instructions for feature engineering, feature discovery, and feature importance analysis. | [SKILL.md](skills/datarobot-feature-engineering/SKILL.md) |
| `skills/datarobot-model-monitoring/` | Tools for monitoring model performance, tracking data drift, and managing model health. | [SKILL.md](skills/datarobot-model-monitoring/SKILL.md) |
| `skills/datarobot-model-explainability/` | Tools for model explainability, prediction explanations, SHAP values, and model diagnostics. | [SKILL.md](skills/datarobot-model-explainability/SKILL.md) |
| `skills/datarobot-data-preparation/` | Utilities for data upload, dataset management, and data validation. | [SKILL.md](skills/datarobot-data-preparation/SKILL.md) |
| `skills/datarobot-app-framework-cicd/` | Set up CI/CD pipelines for DataRobot application templates with GitLab and GitHub Actions. | [SKILL.md](skills/datarobot-app-framework-cicd/SKILL.md) |

## Using skills in your coding agent

Once a skill is installed, mention it directly in your instructions to the coding agent:

- "Use the DataRobot model training skill to create a new project and start AutoML training."
- "Use the DataRobot predictions skill to generate a prediction dataset template for deployment abc123."
- "Use the DataRobot feature engineering skill to analyze feature importance for my model."
- "Use the DataRobot model monitoring skill to check data drift for deployment xyz789."

Your coding agent automatically loads the corresponding `SKILL.md` instructions and any helper scripts it needs while completing the task.

### Helper scripts

Some skills include helper scripts that an agent can run directly:

- **datarobot-predictions**: `get_deployment_features.py`, `generate_prediction_data_template.py`, `validate_prediction_data.py`, `make_prediction.py`
- **datarobot-model-training**: `create_project.py`, `start_training.py`, `list_models.py`
- **datarobot-data-preparation**: `upload_dataset.py`

These scripts are located in each skill's `scripts/` directory and can be executed directly or used as references when writing code.

## Contribute or customize a skill

1. Copy one of the existing skill folders (for example, `skills/datarobot-model-training/`) and rename it.
2. Update the new folder's `SKILL.md` frontmatter:

   ```yaml
   ---
   name: datarobot-my-skill-name
   description: Describe what the skill does and when to use it
   ---
   
   # Skill Title
   Guidance + examples + guardrails
   ```

3. **Important:** Follow the naming convention `datarobot-<category>` for all skill names and folder names.
4. Add or edit supporting scripts, templates, and documents referenced by your instructions.
5. Reinstall or reload the skill bundle in your coding agent so the updated folder is available.

## Development & validation

This repository includes automated validation and linting tools to help maintain consistency and quality across all skills.

### Prerequisites

- [Task](https://taskfile.dev/) - Task runner (install: `brew install go-task` or `sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d`)
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Available tasks

Run `task --list` to see the available tasks:

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

### Validation rules

The `bin/validate_skills.py` script enforces the following rules:

1. **Naming convention:** All skill folders must start with `datarobot-`.
2. **Structure:** Each skill must include a `SKILL.md` file.
3. **Frontmatter:** The `name` field in `SKILL.md` must match the folder name.

Example:

```text
datarobot-my-skill/
  └── SKILL.md
      ---
      name: datarobot-my-skill  # Must match folder name
      description: ...
      ---
```

### Continuous integration

This repository uses GitHub Actions for automated checks:

- **[Validate Skills](.github/workflows/validate-skills.yml)** - Validates skill naming and structure on every push and pull request.
- **[Trivy Security Scan](.github/workflows/trivy-scan.yml)** - Scans for secrets and security issues daily and on every push and pull request.

All checks must pass before merging pull requests.

## How skills work with DataRobot

Skills guide your coding agent to use the **DataRobot Python SDK** directly. The agent will:

1. Install the `datarobot` Python package if needed.
2. Use the SDK based on skill instructions and examples.
3. Write and execute Python code to interact with DataRobot.

For example, when you ask, "Generate a prediction dataset template," the agent reads `skills/datarobot-predictions/SKILL.md`, then writes Python code with the `datarobot` SDK to retrieve deployment features and generate the template.

### Optional: MCP server support

If you have a DataRobot MCP server running, agents can also use MCP tools instead of calling the SDK directly. See the [MCP Server Template](https://github.com/datarobot-community/datarobot-mcp-template) for more information.

## Runtime prerequisites

To use DataRobot skills, you need:

- **A DataRobot account** with API access
- **A DataRobot API token** and endpoint
- **A Python environment** where your coding agent can install packages

The agent will automatically install the `datarobot` Python package when needed.

## Additional documentation

- [Usage Guide](docs/USAGE_GUIDE.md) - A complete guide to using DataRobot skills
- [LangGraph Integration](docs/LANGGRAPH_INTEGRATION.md) - How to use skills with LangGraph agents
- [Agent Framework Integration](docs/AGENT_FRAMEWORK_INTEGRATION.md) - Patterns for LangGraph, PydanticAI, and other programmatic agent frameworks

## Additional references

- Browse the latest instructions, scripts, and templates at [datarobot-oss/datarobot-agent-skills](https://github.com/datarobot-oss/datarobot-agent-skills).
- Review the [DataRobot documentation](https://docs.datarobot.com/) for the libraries and workflows referenced in each skill.
- See the [DataRobot Python SDK documentation](https://datarobot-public-api-client.readthedocs-hosted.com/) for API reference.
