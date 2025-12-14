# DataRobot Skills for Codex

This file provides instructions for OpenAI Codex to use DataRobot skills. Codex will automatically load these instructions when working with DataRobot-related tasks.

## Available Skills

### dr-model-training
Use this skill when working with model training, project creation, AutoML configuration, or model selection tasks.

### dr-model-deployment
Use this skill when deploying models, managing deployments, or configuring prediction environments.

### dr-predictions
Use this skill when making predictions, generating prediction datasets, or validating prediction data.

### dr-feature-engineering
Use this skill when analyzing feature importance, understanding feature engineering, or optimizing feature sets.

### dr-model-monitoring
Use this skill when monitoring model performance, tracking data drift, or managing model health.

### dr-data-preparation
Use this skill when uploading datasets, validating data, or preparing data for DataRobot projects.

### dr-model-explainability
Use this skill when analyzing model explainability, getting prediction explanations, SHAP values, or generating model diagnostics.

## How to Use

When a user requests a DataRobot-related task:

1. **Identify the appropriate skill(s)** and load the corresponding `SKILL.md` file
2. **Follow the skill's guidance** to use the DataRobot Python SDK directly
3. **Install the SDK** if needed: `pip install datarobot`
4. **Use the code examples** provided in each skill to write Python code
5. **Execute the code** using the DataRobot SDK based on skill instructions

Skills provide instructions, workflows, and code examples - the agent writes and executes Python code using the DataRobot SDK.

## Skill Selection Guide

- **Training models**: Use `dr-model-training`
- **Deploying models**: Use `dr-model-deployment`
- **Making predictions**: Use `dr-predictions`
- **Feature analysis**: Use `dr-feature-engineering`
- **Monitoring models**: Use `dr-model-monitoring`
- **Data management**: Use `dr-data-preparation`
- **Model explainability**: Use `dr-model-explainability`

For complex tasks, you may need to use multiple skills in sequence.

## SDK Usage

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

