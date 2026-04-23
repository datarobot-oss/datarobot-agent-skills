<p align="center">
  <a href="https://github.com/datarobot-oss/datarobot-agent-skills">
    <img src="https://af.datarobot.com/img/datarobot_logo.avif" width="600px" alt="DataRobot Logo"/>
  </a>
</p>
<p align="center">
    <span style="font-size: 1.5em; font-weight: bold; display: block;">DataRobot Agent Skills</span>
</p>

<p align="center">
  <a href="https://datarobot.com">Homepage</a>
  ·
  <a href="https://docs.datarobot.com">Documentation</a>
  ·
  <a href="https://docs.datarobot.com/en/docs/get-started/troubleshooting/general-help.html">Support</a>
</p>

<p align="center">
  <a href="https://join.slack.com/t/datarobot-community/shared_invite/zt-3uzfp8k50-SUdMqeux25ok9_5wr4okrg">
    <img src="https://img.shields.io/badge/%23skills-a?label=Slack&labelColor=30373D&color=81FBA6" alt="Slack #skills">
  </a>
</p>

Agentic skills for DataRobot enterprise AI and agent workflows.

```bash
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills
```

## Overview

Agentic skills are modular, task-specific capability packages that help an AI agent move from general reasoning to reliable execution. Each skill bundles instructions, examples, and supporting resources so that the agent can load only what it needs for the current task, reducing context overload and improving tool use within a given workflow.

DataRobot skills are Agent Context Protocol (ACP) definitions for enterprise AI and agent workflows, including building, deploying, and governing agents, as well as AI/ML tasks such as model training, deployment, predictions, feature engineering, and monitoring. They work with major coding agents, including OpenAI Codex, Anthropic Claude Code, Google Gemini CLI, Cursor, and VS Code Copilot.

> [!NOTE]
> "Skills" is an Anthropic term used in Claude AI and Claude Code, but the concept applies more broadly. OpenAI Codex uses `AGENTS.md` to define agent instructions, and Gemini uses `gemini-extension.json` for extensions. This repository is compatible with all of them, and more.

## Quick start

> [!NOTE]
> Supported agents for DataRobot skills include: [Claude Code](https://www.anthropic.com/claude-code/), [Cursor](https://cursor.com), [Codex](https://developers.openai.com/codex/), [Amp](https://ampcode.com/), [VS Code Copilot (GitHub Copilot)](https://github.com/features/copilot), [Gemini CLI](https://geminicli.com/), [Goose](https://block.github.io/goose/), [Letta](https://www.letta.com/), [Kilo Code](https://kilocode.ai/), and [OpenCode](https://opencode.ai/).

Install all DataRobot skills, or only the ones you need, for **all** your AI agents with one command by using the [universal skills installer](https://github.com/skillcreatorai/Ai-Agent-Skills).

**For all skills:**

```bash
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills
```

**For a specific skill:**

```bash
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills/datarobot-predictions
```

**For a specific agent:**

```bash
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills --agent cursor
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills --agent claude
```

> [!NOTE]
> By default, the installer copies skills to all supported agents at the same time. No configuration is required.
> For agent-specific installation methods, see the [Installation to your coding agent](#installation-to-your-coding-agent) section below.

### How do skills work?

Skills are self-contained folders that package instructions, scripts, and resources for a specific use case. Each folder includes a `SKILL.md` file with YAML frontmatter (`name` and `description`), followed by the guidance your coding agent uses while the skill is active.

> [!NOTE]
> All DataRobot skills follow the naming convention `datarobot-<category>`, where `<category>` describes the skill's focus area. This provides clear identification of DataRobot-specific skills, consistent naming across the skill library, and easy discovery and organization.

### Installation to your coding agent

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

For more details, see the [Codex `AGENTS.md`](https://developers.openai.com/codex/guides/agents-md) documentation.

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

See the [Gemini CLI extensions](https://geminicli.com/docs/extensions/) documentation for more information.

</details>

<details><summary><strong>Cursor</strong></summary>

Cursor can automatically detect and use skills from this repository in two main ways:

**Option 1: Use `AGENTS.md`**

> NOTE: This option is the recommended approach.

When you open this repository as your workspace, Cursor automatically reads the `AGENTS.md` file. The skills are available immediately without additional configuration.

To verify that the skills are loaded:

1. Open Cursor in this repository.
2. Open the AI chat panel (`Cmd/Ctrl + L`).
3. Ask: "What DataRobot skills are available?"

**Option 2: Use `.cursorrules`**

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
- datarobot-external-agent-monitoring: External agent OTel instrumentation for DataRobot monitoring

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

> [!TIP]
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
| `skills/datarobot-external-agent-monitoring/` | Instrument any external AI agent with OpenTelemetry to send traces, logs, and metrics to DataRobot for monitoring and observability. Supports Google ADK, LangChain, LangGraph, CrewAI, LlamaIndex, PydanticAI, and generic Python agents. | [SKILL.md](skills/datarobot-external-agent-monitoring/SKILL.md) |

## Using skills in your coding agent

Once a skill is installed, mention it directly in your instructions to the coding agent:

- "Use the DataRobot model training skill to create a new project and start AutoML training."
- "Use the DataRobot predictions skill to generate a prediction dataset template for deployment abc123."
- "Use the DataRobot feature engineering skill to analyze feature importance for my model."
- "Use the DataRobot model monitoring skill to check data drift for deployment xyz789."
- "Use the DataRobot external agent monitoring skill to instrument my agent for DataRobot monitoring."

Your coding agent automatically loads the corresponding `SKILL.md` instructions and any helper scripts it needs while completing the task.

### Helper scripts

Some skills include helper scripts that an agent can run directly:

- **datarobot-predictions**: `get_deployment_features.py`, `generate_prediction_data_template.py`, `validate_prediction_data.py`, `make_prediction.py`
- **datarobot-model-training**: `create_project.py`, `start_training.py`, `list_models.py`
- **datarobot-data-preparation**: `upload_dataset.py`
- **datarobot-external-agent-monitoring**: `create_shell_deployment.py`, `verify_otel_connection.py`

These scripts are located in each skill's `scripts/` directory and can be executed directly or used as references when writing code.

## Additional documentation

- [Usage Guide](docs/USAGE_GUIDE.md) - A complete guide to using DataRobot skills
- [LangGraph Integration](docs/LANGGRAPH_INTEGRATION.md) - How to use skills with LangGraph agents
- [Agent Framework Integration](docs/AGENT_FRAMEWORK_INTEGRATION.md) - Patterns for LangGraph, PydanticAI, and other programmatic agent frameworks
- [Development and customization](docs/DEVELOPMENT_AND_CUSTOMIZATION.md) - How to customize skills, run validation, understand DataRobot skill execution, and review runtime prerequisites

## Additional references

- Browse the latest instructions, scripts, and templates at [datarobot-oss/datarobot-agent-skills](https://github.com/datarobot-oss/datarobot-agent-skills).
- Review the [DataRobot documentation](https://docs.datarobot.com/) for the libraries and workflows referenced in each skill.
- See the [DataRobot Python SDK documentation](https://datarobot-public-api-client.readthedocs-hosted.com/) for API reference.
