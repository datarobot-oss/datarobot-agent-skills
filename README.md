# DataRobot Skills

DataRobot Skills are Agent Context Protocol (ACP) definitions for AI/ML tasks like model training, deployment, predictions, feature engineering, and model monitoring. They are interoperable with all major coding agent tools like OpenAI Codex, Anthropic's Claude Code, Google DeepMind's Gemini CLI, and Cursor.

## How do Skills work?

In practice, skills are self-contained folders that package instructions, scripts, and resources together for an AI agent to use on a specific use case. Each folder includes a `SKILL.md` file with YAML frontmatter (name and description) followed by the guidance your coding agent follows while the skill is active.

> **Note**: 'Skills' is actually an Anthropic term used within Claude AI and Claude Code and not adopted by other agent tools, but we love it! OpenAI Codex uses an `AGENTS.md` file to define the instructions for your coding agent. Google Gemini uses 'extensions' to define the instructions for your coding agent in a `gemini-extension.json` file. This repo is compatible with all of them, and more!

## Installation

DataRobot skills are compatible with Claude Code, Codex, and Gemini CLI. With integrations Cursor, Windsurf, and Continue, on the way.

### Claude Code

Register the repository as a plugin marketplace:
```
/plugin marketplace add datarobot/skills
```

To install a skill, run:
```
/plugin install <skill-folder>@datarobot-skills
```

For example:
```
/plugin install dr-model-training@datarobot-skills
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
gemini extensions install https://github.com/datarobot/skills.git --consent
```

See Gemini CLI extensions docs for more help.

## Skills

This repository contains skills for common DataRobot workflows. You can also contribute your own skills to the repository.

### Available skills

| Skill Folder | Description | Documentation |
|-------------|-------------|--------------|
| `dr-model-training/` | Instructions and utilities for training models, managing projects, and running AutoML experiments. | [SKILL.md](dr-model-training/SKILL.md) |
| `dr-model-deployment/` | Tools for deploying models, managing deployments, and configuring prediction environments. | [SKILL.md](dr-model-deployment/SKILL.md) |
| `dr-predictions/` | Guidance for making predictions, batch scoring, real-time predictions, and generating prediction datasets. | [SKILL.md](dr-predictions/SKILL.md) |
| `dr-feature-engineering/` | Instructions for feature engineering, feature discovery, and feature importance analysis. | [SKILL.md](dr-feature-engineering/SKILL.md) |
| `dr-model-monitoring/` | Tools for monitoring model performance, tracking data drift, and managing model health. | [SKILL.md](dr-model-monitoring/SKILL.md) |
| `dr-model-explainability/` | Tools for model explainability, prediction explanations, SHAP values, and model diagnostics. | [SKILL.md](dr-model-explainability/SKILL.md) |
| `dr-data-preparation/` | Utilities for data upload, dataset management, and data validation. | [SKILL.md](dr-data-preparation/SKILL.md) |

## Using skills in your coding agent

Once a skill is installed, mention it directly while giving your coding agent instructions:

- "Use the DataRobot model training skill to create a new project and start AutoML training."
- "Use the DataRobot predictions skill to generate a prediction dataset template for deployment abc123."
- "Use the DataRobot feature engineering skill to analyze feature importance for my model."
- "Use the DataRobot model monitoring skill to check data drift for deployment xyz789."

Your coding agent automatically loads the corresponding `SKILL.md` instructions and helper scripts while it completes the task.

### Helper Scripts

Some skills include executable helper scripts that Claude can run directly:

- **dr-predictions**: `get_deployment_features.py`, `generate_prediction_data_template.py`, `validate_prediction_data.py`, `make_prediction.py`
- **dr-model-training**: `create_project.py`, `start_training.py`, `list_models.py`
- **dr-data-preparation**: `upload_dataset.py`

These scripts are located in each skill's `scripts/` directory and can be executed directly or used as reference when writing code.

## Contribute or customize a skill

1. Copy one of the existing skill folders (for example, `dr-model-training/`) and rename it.
2. Update the new folder's `SKILL.md` frontmatter:
   ```yaml
   ---
   name: my-skill-name
   description: Describe what the skill does and when to use it
   ---
   
   # Skill Title
   Guidance + examples + guardrails
   ```
3. Add or edit supporting scripts, templates, and documents referenced by your instructions.
4. Reinstall or reload the skill bundle in your coding agent so the updated folder is available.

## How Skills Work

Skills guide your coding agent to use the **DataRobot Python SDK** directly. The agent will:

1. Install the `datarobot` Python package if needed
2. Use the SDK based on skill instructions and examples
3. Write and execute Python code to interact with DataRobot

**Example**: When you ask "Generate a prediction dataset template", the agent reads `dr-predictions/SKILL.md`, then writes Python code using `datarobot` SDK to get deployment features and generate the template.

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

- Browse the latest instructions, scripts, and templates directly at [datarobot/skills](https://github.com/datarobot/skills).
- Review [DataRobot documentation](https://docs.datarobot.com/) for the specific libraries or workflows you reference inside each skill.
- Check out the [DataRobot Python SDK Documentation](https://datarobot-public-api-client.readthedocs-hosted.com/) for API reference

