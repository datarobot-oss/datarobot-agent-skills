---
name: datarobot-model-deployment
description: Tools and guidance for deploying DataRobot models, managing deployments, configuring prediction environments, and deployment operations. Use when deploying models, creating or updating deployments, or configuring prediction environments.
---

# DataRobot Model Deployment Skill

This skill provides comprehensive guidance for deploying models, managing deployment configurations, and operating production deployments.

## Quick Start

**Most common use case**: Deploy a trained model to production

1. **Get best model**: `dr.ModelRecommendation.get(project_id).get_model()` to get the recommended model
2. **Register the model**: `dr.RegisteredModelVersion.create_for_leaderboard_item(model_id=..., name=...)` to create a registered model version
3. **Create deployment**: `dr.Deployment.create_from_registered_model_version(model_package_id=version.id, label=..., default_prediction_server_id=...)` to deploy it
4. **Get endpoint**: `(deployment.default_prediction_server or {}).get("url")` to retrieve the prediction URL (`None` for DataRobot Serverless deployments)

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
1. Get DataRobot's recommended model from the project (`dr.ModelRecommendation.get(project_id).get_model()`)
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
python -m pip install datarobot
```

If the environment has no pip (uv-created venvs, PEP 668 systems), use `uv pip install datarobot` instead.

### Key SDK Operations

Use these DataRobot SDK methods for deployment management:

**Deployments**:
- `dr.RegisteredModelVersion.create_for_leaderboard_item(model_id, name)` - Register a model for deployment (`dr.Deployment.create_from_learning_model` is deprecated — do not use it)
- `dr.Deployment.create_from_registered_model_version(model_package_id, label, default_prediction_server_id=...)` - Create deployment. `default_prediction_server_id` is typed Optional but DataRobot Cloud returns a 422 error without it; for DataRobot Serverless, pass `prediction_environment_id=...` instead
- `dr.PredictionServer.list()` - List prediction servers; objects expose only `.id`, `.url`, and `.datarobot_key` (no `.name`)
- `dr.Deployment.get(deployment_id)` - Get deployment details
- `dr.Deployment.list()` - List all deployments (optionally `search=<label substring>`; deployments cannot be filtered by project id via the SDK)
- `deployment.delete()` - Delete deployment

**Model Replacement (champion swap)**:
- `deployment.validate_replacement_model(new_model_id=...)` - Validate replacement eligibility
- `deployment.perform_model_replace(new_registered_model_version_id=..., reason=...)` - Replace champion model (async). Register the new model first via `dr.RegisteredModelVersion.create_for_leaderboard_item(model_id=..., registered_model_id=<deployed registered model>)` and pass the version's id — a leaderboard model id is rejected. `reason` takes a `dr.enums.MODEL_REPLACEMENT_REASON` value (`ACCURACY`, `DATA_DRIFT`, `ERRORS`, `OTHER`, `SCHEDULED_REFRESH`, `SCORING_SPEED`)

**Challenger Models (limited via SDK)**:
- `deployment.list_challengers()` - List challenger models (if enabled/configured)
- `deployment.get_challenger_models_settings()` / `deployment.update_challenger_models_settings(...)` - Configure challenger models settings

**Deployment Info**:
- `deployment.get_features()` - Get required features
- `deployment.default_prediction_server` - Prediction endpoint info: a dict with `"url"` and `"datarobot-key"` keys (kebab-case; the key is sent as a request header), or `None` for DataRobot Serverless deployments

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

# Initialize client
dr.Client()

# Get DataRobot's recommended model from the project
best_model = dr.ModelRecommendation.get("abc123").get_model()

# Register the model (required before deploying)
registered_version = dr.RegisteredModelVersion.create_for_leaderboard_item(
    model_id=best_model.id, name="Sales Prediction v1"
)

# DataRobot Cloud requires a prediction server (the param is typed Optional but the API 422s without it)
servers = dr.PredictionServer.list()  # PredictionServer has ONLY .id, .url, .datarobot_key (no .name)

# Create deployment
deployment = dr.Deployment.create_from_registered_model_version(
    model_package_id=registered_version.id,
    label="Sales Prediction v1",
    description="Production deployment for sales forecasting",
    default_prediction_server_id=servers[0].id,
)

print(f"Deployment created: {deployment.id}")
```

For DataRobot Serverless, pass `prediction_environment_id=<serverless prediction environment id>` instead of `default_prediction_server_id`.

### Pattern 2: Deployment with challenger
```python
import datarobot as dr

# Register the primary model, then create the deployment
registered_version = dr.RegisteredModelVersion.create_for_leaderboard_item(
    model_id=primary_model.id, name="Sales Prediction v2"
)
deployment = dr.Deployment.create_from_registered_model_version(
    model_package_id=registered_version.id,
    label="Sales Prediction v2",
    default_prediction_server_id=dr.PredictionServer.list()[0].id,
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
python -m pip install datarobot
```

If the environment has no pip (uv-created venvs, PEP 668 systems), use `uv pip install datarobot` instead.

### Initialize Client

```python
import datarobot as dr

dr.Client()
```

## Resources

- [DataRobot Python SDK Documentation](https://datarobot-public-api-client.readthedocs-hosted.com/)
- [DataRobot Deployment Documentation](https://docs.datarobot.com/en/docs/mlops/deployment/deploy-methods/add-deploy-info.html)
- [Prediction Environments Guide](https://docs.datarobot.com/en/docs/mlops/deployment/prediction-env/pred-env-deploy.html)
- [Challenger Models Documentation](https://docs.datarobot.com/en/docs/mlops/monitor/challengers.html)

