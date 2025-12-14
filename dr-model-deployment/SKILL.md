---
name: dr-model-deployment
description: Tools and guidance for deploying DataRobot models, managing deployments, configuring prediction environments, and deployment operations.
---

# DataRobot Model Deployment Skill

This skill provides comprehensive guidance for deploying models, managing deployment configurations, and operating production deployments.

## Quick Start

**Most common use case**: Deploy a trained model to production

1. **Get best model**: Find the best model from a project (highest metric score)
2. **Create deployment**: `create_deployment(model_id, deployment_name)` to deploy model
3. **Get endpoint**: `get_deployment_endpoint(deployment_id)` to retrieve prediction URL

**Example**: "Deploy the best model from project abc123 as 'Sales Prediction v1'"

## When to use this skill

Use this skill when you need to:
- Deploy trained models to production
- Configure deployment settings and environments
- Manage multiple deployments
- Replace a deployment’s champion model with a new model version
- Configure prediction servers and environments
- Monitor deployment health and status
- Manage deployment access and permissions

## Key capabilities

### 1. Deployment Creation

- Deploy models from projects or registered models
- Choose prediction environment (DataRobot Serverless, external)
- Configure deployment settings (challenger models, A/B testing)
- Set up deployment metadata and descriptions

### 2. Deployment Configuration

- Configure prediction servers and environments
- Set up batch prediction settings
- Configure real-time prediction endpoints
- Manage deployment credentials and access

### 3. Deployment Management

- Replace deployment champion model (model swap)
- Enable/disable deployments
- Manage challenger models for A/B testing
- Configure replacement policies

### 4. Deployment Operations

- Get deployment information and status
- Retrieve deployment endpoints
- Manage deployment settings
- Handle deployment errors and issues

## Workflow examples

### Example 1: Deploy a model to production

**User request**: "Deploy the best model from project abc123 to production with the name 'Sales Prediction v1'."

**Agent workflow**:
1. Get the best model from the project (highest metric score)
2. Create a new deployment with the model
3. Configure deployment settings (name, description, environment)
4. Set up prediction environment (DataRobot Serverless recommended)
5. Retrieve deployment endpoint and credentials
6. Verify deployment is active and ready for predictions

### Example 2: Update deployment with new model

**User request**: "Replace the model in deployment xyz789 with the latest model from project abc123."

**Agent workflow**:
1. Get the latest model from the project
2. Retrieve current deployment information
3. Validate the replacement model is eligible (`deployment.validate_replacement_model(...)`)
4. Perform model replacement (`deployment.perform_model_replace(...)`)
5. Verify replacement completed successfully
6. Report deployment update status

## Using DataRobot SDK

This skill guides you to use the DataRobot Python SDK directly. Install the SDK if needed:

```bash
pip install datarobot
```

### Key SDK Operations

Use these DataRobot SDK methods for deployment management:

**Deployments**:
- `dr.Deployment.create_from_learning_model(model_id, label)` - Create deployment
- `dr.Deployment.get(deployment_id)` - Get deployment details
- `dr.Deployment.list(project_id)` - List deployments
- `deployment.delete()` - Delete deployment

**Model Replacement (champion swap)**:
- `deployment.validate_replacement_model(new_model_id=...)` - Validate replacement eligibility
- `deployment.perform_model_replace(new_model_id=..., reason=...)` - Replace champion model (async)

**Challenger Models (limited via SDK)**:
- `deployment.list_challengers()` - List challenger models (if enabled/configured)
- `deployment.get_challenger_models_settings()` / `deployment.update_challenger_models_settings(...)` - Configure challenger models settings

**Deployment Info**:
- `deployment.get_features()` - Get required features

See the [Common Patterns](#common-patterns) section below for complete examples.

## Best practices

1. **Naming conventions**: Use clear, versioned names for deployments
2. **Environment selection**: Choose appropriate prediction environment for your use case
3. **Challenger models**: Use challenger models to test new models before full replacement
4. **Monitoring**: Set up monitoring and alerts for production deployments
5. **Documentation**: Document deployment purpose, model version, and configuration
6. **Access control**: Configure appropriate access permissions for deployments

## Common patterns

### Pattern 1: Standard deployment
```python
import datarobot as dr
import os

# Initialize client
client = dr.Client(
    token=os.getenv("DATAROBOT_API_TOKEN"),
    endpoint=os.getenv("DATAROBOT_ENDPOINT")
)

# Get best model from project
models = dr.Model.list("abc123")
best_model = max(models, key=lambda m: m.metrics.get('AUC', 0))

# Create deployment
deployment = dr.Deployment.create_from_learning_model(
    model_id=best_model.id,
    label="Sales Prediction v1",
    description="Production deployment for sales forecasting"
)

print(f"Deployment created: {deployment.id}")
```

### Pattern 2: Deployment with challenger
```python
import datarobot as dr

# Create deployment with primary model
deployment = dr.Deployment.create_from_learning_model(
    model_id=primary_model.id,
    label="Sales Prediction v2"
)

# List challengers (if challenger models are configured/enabled)
challengers = deployment.list_challengers()
print(f"Challengers: {len(challengers)}")
```

## Deployment environments

### DataRobot Serverless
- Fully managed prediction environment
- Automatic scaling
- No infrastructure management
- Recommended for most use cases

### External deployment
- Deploy to your own infrastructure
- More control over resources
- Requires infrastructure management
- Use for specific compliance or performance requirements

## Deployment lifecycle

1. **Create**: Deploy model to production environment
2. **Monitor**: Track predictions, performance, and health
3. **Update**: Replace with new model versions as needed
4. **Retire**: Disable or archive old deployments

## Error handling

Common errors and solutions:

- **Model not found**: Verify model ID and project access
- **Deployment creation failures**: Check prediction environment availability
- **Endpoint access issues**: Verify credentials and permissions
- **Update failures**: Ensure new model is compatible with deployment settings

## SDK Setup

### Install DataRobot SDK

```bash
pip install datarobot
```

### Initialize Client

```python
import datarobot as dr
import os

client = dr.Client(
    token=os.getenv("DATAROBOT_API_TOKEN"),
    endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com")
)
```

## Resources

- [DataRobot Python SDK Documentation](https://datarobot-public-api-client.readthedocs-hosted.com/)
- [DataRobot Deployment Documentation](https://docs.datarobot.com/en/docs/deploy/index.html)
- [Prediction Environments Guide](https://docs.datarobot.com/en/docs/deploy/pred-environments/index.html)
- [Challenger Models Documentation](https://docs.datarobot.com/en/docs/deploy/challengers/index.html)

