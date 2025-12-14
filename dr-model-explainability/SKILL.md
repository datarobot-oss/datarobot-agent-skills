---
name: dr-model-explainability
description: Tools and guidance for model explainability, prediction explanations, feature impact analysis, SHAP values, and model diagnostics.
---

# DataRobot Model Explainability Skill

This skill provides comprehensive guidance for understanding model decisions, analyzing prediction explanations, and interpreting model behavior using various explainability techniques.

## Quick Start

**Most common use case**: Get prediction explanations for a specific prediction

1. **Identify model/project**: Get `project_id` + `model_id` (from a deployment’s champion model, or from training)
2. **Compute explanations**: Use `dr.PredictionExplanations.create(project_id, model_id, dataset_id, ...)`
3. **Read explanation rows**: Use `dr.PredictionExplanations.get(project_id, prediction_explanations_id)` and iterate `get_rows()`

**Example**: "Explain why the model predicted 0.85 for this customer record"

## When to use this skill

Use this skill when you need to:
- Understand why a model made a specific prediction
- Analyze feature contributions to predictions (SHAP values)
- Generate prediction explanations for stakeholders
- Understand model behavior and decision-making
- Generate model diagnostics (ROC curves, lift charts, confusion matrices)
- Analyze partial dependence and feature interactions
- Meet regulatory compliance requirements for model explainability

## Key capabilities

### 1. Prediction Explanations

- Get SHAP (SHapley Additive exPlanations) values for individual predictions
- Understand feature contributions to each prediction
- Generate human-readable explanations
- Export explanations for reporting

### 2. Feature Impact Analysis

- Analyze how individual features impact predictions
- Compare feature importance across different predictions
- Understand feature interactions
- Identify key drivers for model decisions

### 3. Model Diagnostics

- Generate ROC curves for classification models
- Create lift charts and gain charts
- Generate confusion matrices
- Analyze model calibration
- Create partial dependence plots
- Generate ICE (Individual Conditional Expectation) plots

### 4. Global Model Understanding

- Understand overall model behavior
- Analyze feature importance at model level
- Compare explainability across models
- Generate model interpretability reports

## Workflow examples

### Example 1: Explain a specific prediction

**User request**: "Why did the model predict 0.85 probability for customer ID 12345?"

**Agent workflow**:
1. Get the prediction record for customer 12345
2. Retrieve prediction explanations (SHAP values) for this prediction
3. Sort features by contribution (positive/negative impact)
4. Explain which features increased the prediction and which decreased it
5. Provide human-readable summary of the explanation

### Example 2: Generate model diagnostics

**User request**: "Generate ROC curve and confusion matrix for model xyz123"

**Agent workflow**:
1. Get model information and validation data
2. Generate ROC curve with AUC score
3. Generate confusion matrix with precision/recall metrics
4. Create lift chart showing model performance
5. Compile diagnostics into a report

## Using DataRobot SDK

This skill guides you to use the DataRobot Python SDK directly. Install the SDK if needed:

```bash
pip install datarobot
```

### Key SDK Operations

Use these DataRobot SDK methods for model explainability:

**Prediction Explanations (SDK v3.10.0)**:
- `dr.PredictionExplanations.create(project_id, model_id, dataset_id, ...)` - Compute prediction explanations on a dataset
- `dr.PredictionExplanations.get(project_id, prediction_explanations_id)` - Fetch explanations and read rows
- `prediction_explanations.get_rows()` - Iterate explanation rows

**Model Diagnostics**:
- `model.get_roc_curve(source='validation')` - Get ROC curve with AUC
- `model.get_confusion_matrix()` - Get confusion matrix
- `model.get_lift_chart()` - Get lift chart data
- `model.get_feature_impact()` - Get feature importance

**Feature Analysis**:
- `model.get_partial_dependence(feature_name)` - Get partial dependence data

See the [Common Patterns](#common-patterns) section below for complete examples.

## Best practices

1. **Use SHAP for local explanations**: SHAP values provide the best local (per-prediction) explanations
2. **Combine with global insights**: Use feature importance for global understanding, SHAP for local
3. **Explain in context**: Always explain predictions in the context of the business problem
4. **Visualize explanations**: Use charts and graphs to make explanations more understandable
5. **Document explanations**: Save explanations for compliance and auditing purposes
6. **Compare across models**: Use explainability to compare different models

## Common patterns

### Pattern 1: Get prediction explanations

```python
import datarobot as dr
import os

# Initialize client
client = dr.Client(
    token=os.getenv("DATAROBOT_API_TOKEN"),
    endpoint=os.getenv("DATAROBOT_ENDPOINT")
)

# Example: compute explanations for a dataset (batch)
project_id = "project_id_here"
model_id = "model_id_here"
dataset_id = "dataset_id_here"  # dataset to explain

pe = dr.PredictionExplanations.create(
    project_id=project_id,
    model_id=model_id,
    dataset_id=dataset_id,
    max_explanations=5,
)

pe2 = dr.PredictionExplanations.get(project_id, pe.id)
for row in pe2.get_rows():
    # row contains per-row explanation info
    print(row)
```

### Pattern 2: Generate model diagnostics

```python
import datarobot as dr

# Get model
model = dr.Model.get("xyz123")

# Get ROC curve
roc_curve = model.get_roc_curve(source='validation')
print(f"AUC Score: {roc_curve.auc:.3f}")

# Get confusion matrix (for classification models)
try:
    cm = model.get_confusion_matrix(source='validation')
    print(f"Precision: {cm.precision:.3f}")
    print(f"Recall: {cm.recall:.3f}")
    print(f"F1 Score: {cm.f1_score:.3f}")
except:
    print("Confusion matrix not available for this model type")

# Get lift chart
lift_chart = model.get_lift_chart(source='validation')
print(f"Lift at 10%: {lift_chart.lift[10]:.3f}")
```

## Understanding SHAP Values

SHAP (SHapley Additive exPlanations) values explain the output of any machine learning model:

- **Positive SHAP value**: Feature increases the prediction
- **Negative SHAP value**: Feature decreases the prediction
- **Magnitude**: Larger absolute values indicate stronger impact
- **Sum**: SHAP values sum to the difference between prediction and baseline

Example interpretation:
- Feature "age" has SHAP value +0.15 → Age increases prediction by 0.15
- Feature "income" has SHAP value -0.08 → Income decreases prediction by 0.08

## Model Diagnostics Explained

### ROC Curve
- **Purpose**: Evaluate classification model performance
- **AUC Score**: Area under curve (0-1), higher is better
- **Use**: Compare models, select optimal threshold

### Confusion Matrix
- **Purpose**: Show classification accuracy breakdown
- **Metrics**: Precision, Recall, F1-Score
- **Use**: Understand model errors and biases

### Lift Chart
- **Purpose**: Show model performance vs. baseline
- **Use**: Evaluate model value, select top predictions

### Partial Dependence
- **Purpose**: Show how a feature affects predictions on average
- **Use**: Understand feature relationships and interactions

## Error handling

Common errors and solutions:

- **Prediction not found**: Ensure prediction_id is valid and accessible
- **Explanations unavailable**: Some model types don't support explanations
- **Feature not found**: Verify feature name matches model features
- **Insufficient data**: Need validation data for some diagnostics

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
- [DataRobot Model Insights Documentation](https://docs.datarobot.com/en/docs/modeling/analyze-models/index.html)
- [Prediction Explanations Guide](https://docs.datarobot.com/en/docs/predictions/pred-explanations/index.html)
- [SHAP Documentation](https://shap.readthedocs.io/)

