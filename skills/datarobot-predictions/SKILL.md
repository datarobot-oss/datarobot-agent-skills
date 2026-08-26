---
name: datarobot-predictions
description: Tools and guidance for making predictions with DataRobot deployments, including real-time predictions, batch scoring, prediction dataset generation, and prediction explanations (SHAP/XEMP). Use when making predictions, running batch scoring, generating prediction datasets, or explaining individual predictions from a deployment.
---

# DataRobot Predictions Skill

This skill provides comprehensive guidance for working with DataRobot predictions, including real-time predictions, batch scoring, and generating prediction datasets.

## Quick Start

**Most common use case**: Generate predictions for a deployment

1. **Get deployment features**: `get_deployment_features(deployment_id)` to understand required columns
2. **Generate template**: `generate_prediction_data_template(deployment_id, n_rows)` to create CSV structure
3. **Make predictions**: Use `deployment.predict_batch(...)` (works for both single-row “real-time” and batch scoring)

**Example**: "Generate a prediction dataset template for deployment abc123 with 10 rows"

**To also explain predictions**: pass `--max-explanations N` to `make_prediction.py` (or the
`max_explanations=N` kwarg in code). See [Prediction Explanations](#prediction-explanations) below.

## When to use this skill

Use this skill when you need to:
- Make predictions from deployed DataRobot models
- Explain individual predictions from a deployment (SHAP or XEMP, per-row)
- Generate prediction dataset templates
- Validate prediction data before scoring
- Understand deployment feature requirements
- Perform batch predictions on large datasets
- Get sample training data to understand expected formats

> For post-hoc explanations against a **training project / leaderboard model** (not a deployment),
> use the `datarobot-model-explainability` skill instead. This skill covers deployment-time
> explanations returned alongside scoring.

## Key capabilities

### 1. Understanding Deployment Requirements

Before making predictions, you need to understand what features a deployment requires:

- **Feature names and types**: Know which columns are needed (numeric, categorical, text, date)
- **Feature importance**: Understand which features matter most
- **Target information**: Know what you're predicting
- **Time series configuration**: If applicable, understand datetime columns and series IDs

### 2. Generating Prediction Datasets

Create properly formatted prediction datasets:

- Generate CSV templates with all required columns
- Include sample values appropriate for each feature type
- Add metadata comments explaining the model structure
- Ensure correct column ordering

### 3. Validating Prediction Data

Validate datasets before making predictions:

- Check for missing required features
- Verify data types match expected types
- Identify missing low-importance features (warnings)
- Note extra columns that will be ignored

### 4. Making Predictions

Execute predictions using various methods:

- **Real-time predictions**: Fast, synchronous predictions for individual records
- **Batch predictions**: Process large datasets efficiently
- **Time series predictions**: Handle forecasting scenarios with proper datetime handling

## Workflow examples

### Example 1: Generate prediction dataset for a new scenario

**User request**: "I want to predict sales for next week for store_A with temperatures of 75°F each day and no promotions."

**Agent workflow**:
1. Get deployment features to understand required columns
2. Generate a prediction data template with 7 rows (one week)
3. Fill in the template with user's specific values:
   - Set temperature = 75 for all rows
   - Set promotion = 0 for all rows
   - Set store_id = "store_A" for all rows
   - Set dates for next 7 days
4. Validate the data to ensure it's correct
5. Make predictions using the validated dataset

### Example 2: Batch scoring a CSV file

**User request**: "Score all records in my prediction_data.csv file using deployment abc123."

**Agent workflow**:
1. Validate the CSV file structure matches deployment requirements
2. Upload the file or provide file path
3. Submit batch prediction job
4. Monitor job status
5. Retrieve and return prediction results

## Using DataRobot SDK

This skill guides you to use the DataRobot Python SDK directly. Install the SDK if needed:

```bash
pip install datarobot datarobot-predict
```

### Key SDK Operations

Use these DataRobot SDK methods to work with predictions:

**Deployment Information**:
- `dr.Deployment.get(deployment_id)` - Get deployment details
- `deployment.get_features()` - Get required features (name/type/importance)

**Predictions**:
- `deployment.predict_batch(source)` - Convenience batch prediction API (CSV path, file object, or pandas DataFrame)
- `dr.BatchPredictionJob.score(deployment=deployment, ...)` - Advanced batch prediction control
- `job.get_result_when_complete()` - Wait for batch scoring to finish and download results

**Data Management**:
- `dr.Dataset.create_from_file(file_path)` - Upload dataset
- `dr.Dataset.get(dataset_id)` - Get dataset info

See the [Common Patterns](#common-patterns) section below for complete examples.

## Prediction Explanations

Deployments can return per-row explanations (top feature contributions) alongside predictions.
Two algorithms are available depending on how the deployment was configured:

- **SHAP** (`shap`): SHapley Additive exPlanations. Available on tree-based models when SHAP was
  enabled at deployment time. Returns signed contributions in the model's score space.
- **XEMP** (`xemp`): DataRobot's eXplainable AI for the eXact Model Prediction. Default when SHAP
  is not enabled. Returns top-N strongest features with a qualitative strength (`+++`, `--`, etc.).

If you omit `explanation_algorithm`, the deployment's default is used.

### How to request explanations

Pass `max_explanations=N` (and any optional filters) when calling `datarobot_predict.deployment.predict`:

```python
import datarobot as dr
import pandas as pd
from datarobot_predict.deployment import predict as dr_predict

dr.Client()
deployment = dr.Deployment.get("abc123")

result = dr_predict(
    deployment=deployment,
    data_frame=pd.DataFrame([{"feature1": 10, "feature2": 20}]),
    max_explanations=3,  # top 3 contributors per row
    explanation_algorithm="shap",  # or "xemp"; omit for deployment default
    # threshold_high=0.8,                # optional: only explain rows scoring > 0.8
    # threshold_low=0.2,                 # optional: only explain rows scoring < 0.2
    # passthrough_columns="all",         # optional: echo input columns through to output
)
print(result.dataframe.to_dict(orient="records"))
```

The result DataFrame includes columns like `EXPLANATION_1_FEATURE_NAME`,
`EXPLANATION_1_ACTUAL_VALUE`, `EXPLANATION_1_STRENGTH`, `EXPLANATION_1_QUALITATIVE_STRENGTH` for
each of the top-N contributors.

### Parameter reference

| Parameter | Purpose |
|-----------|---------|
| `max_explanations` | Top-N contributors per row. `0` (default) disables explanations. |
| `max_ngram_explanations` | Text models only: cap text-segment explanations per row. |
| `threshold_high` | Only explain rows with prediction probability **above** this (0–1). |
| `threshold_low` | Only explain rows with prediction probability **below** this (0–1). |
| `explanation_algorithm` | `"shap"` or `"xemp"`; omit to use deployment default. |
| `passthrough_columns` | `"all"` or set of input column names to echo through to output. |

### CLI shortcut

```bash
python scripts/make_prediction.py abc123 '{"feature1": 10, "feature2": 20}' \
    --max-explanations 3 --explanation-algorithm shap
```

### When to use which threshold

- `threshold_high` is useful when only positive (high-risk / fraud / churn-likely) predictions need
  explaining — saves compute on a large batch.
- `threshold_low` is the mirror image for low-probability rows.
- Setting both restricts explanations to rows outside the `[low, high]` band.

### Common errors

- **"Prediction explanations not enabled"**: the deployment was created without explanations support.
  Re-deploy the model with explanations enabled, or use a deployment that has them.
- **`max_explanations` ignored / no explanation columns in output**: confirm you're calling
  `datarobot_predict.deployment.predict(...)` and that the deployment has explanations enabled.
  The `deployment.predict_batch()` convenience wrapper on the SDK is intended for plain scoring;
  use `datarobot_predict.deployment.predict` when you need explanation kwargs.

## Helper Scripts

This skill includes executable helper scripts that Claude can run directly:

- `scripts/get_deployment_features.py` - Get deployment feature requirements
- `scripts/generate_prediction_data_template.py` - Generate CSV template
- `scripts/validate_prediction_data.py` - Validate prediction data
- `scripts/make_prediction.py` - Make real-time predictions

**Usage example**:
```bash
# Get deployment features
python scripts/get_deployment_features.py abc123

# Generate template
python scripts/generate_prediction_data_template.py abc123 10 template.csv

# Validate data
python scripts/validate_prediction_data.py abc123 prediction_data.csv

# Make prediction
python scripts/make_prediction.py abc123 '{"feature1": 10, "feature2": 20}'

# Make prediction with top-3 SHAP explanations
python scripts/make_prediction.py abc123 '{"feature1": 10, "feature2": 20}' \
    --max-explanations 3 --explanation-algorithm shap
```

Claude can run these scripts directly or use them as reference when writing code.

## Best practices

1. **Always validate first**: Validate prediction data before submitting predictions to catch errors early
2. **Use templates**: Generate templates to ensure correct structure and avoid missing columns
3. **Check feature types**: Ensure numeric features are numbers, categorical features match training values
4. **Handle time series**: For time series models, ensure datetime columns and series IDs are properly formatted
5. **Monitor batch jobs**: For large batch predictions, check job status and handle errors appropriately

## Common patterns

### Pattern 1: Get deployment features and make single prediction (optionally with explanations)
```python
import datarobot as dr
import pandas as pd
from datarobot_predict.deployment import predict as dr_predict

# Initialize client
dr.Client()

deployment = dr.Deployment.get("abc123")

prediction_data = {
    "feature1": value1,
    "feature2": value2,
    # ... all required features (excluding target)
}

# Score one row. Add max_explanations=N to get top-N explanations per row.
result = dr_predict(
    deployment=deployment,
    data_frame=pd.DataFrame([prediction_data]),
    max_explanations=3,  # optional; 0/omit to disable explanations
    explanation_algorithm="shap",  # optional; omit to use deployment default
)
print(result.dataframe.to_dict(orient="records"))
```

### Pattern 2: Generate template and batch predictions
```python
import datarobot as dr
import pandas as pd

# Initialize client
dr.Client()

# Get deployment features
deployment = dr.Deployment.get("abc123")
model = dr.Model.get(deployment.model["id"])
features = model.get_features()

# Create template DataFrame
prediction_features = [f for f in features if f.name != model.target_name]
template_df = pd.DataFrame(columns=[f.name for f in prediction_features])

# Add sample rows
for i in range(100):
    row = {}
    for feature in prediction_features:
        if feature.feature_type == "Numeric":
            row[feature.name] = 0.0
        elif feature.feature_type == "Categorical":
            row[feature.name] = "sample_value"
        else:
            row[feature.name] = ""
    template_df = pd.concat([template_df, pd.DataFrame([row])], ignore_index=True)

# Save template
template_df.to_csv("prediction_template.csv", index=False)

# Fill template with actual data (modify CSV as needed)
# ...

# Submit batch prediction
job = dr.BatchPredictionJob.score(
    deployment_id=deployment.id,
    intake_settings={"type": "localFile", "file": "prediction_template.csv"},
    output_settings={"type": "localFile", "path": "predictions_output.csv"},
)

# Monitor job
job_status = dr.BatchPredictionJob.get(job.id)
print(f"Job status: {job_status.status}")

# Download results when complete
if job_status.status == "completed":
    results = dr.BatchPredictionJob.download(job.id)
```

## Error handling

Common errors and solutions:

- **Missing required features**: Use `get_deployment_features` to get complete list
- **Wrong data types**: Check feature types and convert accordingly
- **Invalid categorical values**: Use training data sample to see valid values
- **Time series format errors**: Ensure datetime format matches training data

## SDK Setup

### Install DataRobot SDK

```bash
pip install datarobot datarobot-predict
```

### Initialize Client

```python
import datarobot as dr

# Initialize client with API credentials
dr.Client()
```

### Environment Variables

Set these environment variables or pass them directly:

- `DATAROBOT_API_TOKEN` - Your DataRobot API token
- `DATAROBOT_ENDPOINT` - Your DataRobot endpoint (default: https://app.datarobot.com)

## Resources

- [DataRobot Python SDK Documentation](https://datarobot-public-api-client.readthedocs-hosted.com/)
- [DataRobot Predictions Documentation](https://docs.datarobot.com/en/docs/predictions/index.html)
- [DataRobot API Reference](https://docs.datarobot.com/en/docs/api/reference/index.html)
- [Batch Predictions Guide](https://docs.datarobot.com/en/docs/api/reference/sdk/batch-predictions.html)

