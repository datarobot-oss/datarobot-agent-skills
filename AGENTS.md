# DataRobot skills for Codex

This file provides instructions for OpenAI Codex to use DataRobot skills. Codex will automatically load these instructions when working with DataRobot-related tasks.

## Naming Convention

All DataRobot skills follow the naming convention `datarobot-<category>` where `<category>` describes the skill's focus area. This ensures:
- Clear identification of DataRobot-specific skills
- Consistent naming across the skill library
- Easy discovery and organization

## Available Skills

### datarobot-model-training
Use this skill when working with model training, project creation, AutoML configuration, or model selection tasks.

### datarobot-model-deployment
Use this skill when deploying models, managing deployments, or configuring prediction environments.

### datarobot-predictions
Use this skill when making predictions, generating prediction datasets, or validating prediction data.

### datarobot-feature-engineering
Use this skill when analyzing feature importance, understanding feature engineering, or optimizing feature sets.

### datarobot-model-monitoring
Use this skill when monitoring model performance, tracking data drift, or managing model health.

### datarobot-data-preparation
Use this skill when uploading datasets, validating data, or preparing data for DataRobot projects.

### datarobot-model-explainability
Use this skill when analyzing model explainability, getting prediction explanations, SHAP values, or generating model diagnostics.

### datarobot-app-framework-cicd
Use this skill when setting up CI/CD pipelines for DataRobot application templates, configuring GitLab or GitHub Actions workflows, managing Pulumi infrastructure, or implementing review deployments and continuous delivery.

### datarobot-external-agent-monitoring
Use this skill when instrumenting external AI agents for DataRobot monitoring. Supports Google ADK, LangChain, LangGraph, CrewAI, LlamaIndex, PydanticAI, and generic Python agents. Creates shell deployments and configures OpenTelemetry to send traces, logs, and metrics to DataRobot.

## How to Use

When a user requests a DataRobot-related task:

1. **Identify the appropriate skill(s)** and load the corresponding `SKILL.md` file from the `skills/` directory
2. **Follow the skill's guidance** to use the DataRobot Python SDK directly
3. **Install the SDK** if needed: `pip install datarobot`
4. **Use the code examples** provided in each skill to write Python code
5. **Execute the code** using the DataRobot SDK based on skill instructions

Skills provide instructions, workflows, and code examples - the agent writes and executes Python code using the DataRobot SDK.

## Skill Selection Guide

- **Training models**: Use `datarobot-model-training`
- **Deploying models**: Use `datarobot-model-deployment`
- **Making predictions**: Use `datarobot-predictions`
- **Feature analysis**: Use `datarobot-feature-engineering`
- **Monitoring models**: Use `datarobot-model-monitoring`
- **Data management**: Use `datarobot-data-preparation`
- **Model explainability**: Use `datarobot-model-explainability`
- **CI/CD for application templates**: Use `datarobot-app-framework-cicd`
- **External agent monitoring**: Use `datarobot-external-agent-monitoring`

For complex tasks, you may need to use multiple skills in sequence.

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

