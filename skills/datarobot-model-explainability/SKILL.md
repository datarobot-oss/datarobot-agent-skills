---
name: datarobot-model-explainability
description: Tools and guidance for model explainability, prediction explanations, feature impact analysis, SHAP values, and model diagnostics. Use when analyzing model explanations, feature impact, SHAP values, or diagnosing model behavior.
---

# DataRobot Model Explainability Skill

This skill provides comprehensive guidance for understanding model decisions, analyzing prediction explanations, and interpreting model behavior using various explainability techniques.

## Quick Start

**Most common use case**: Get SHAP explanations for a leaderboard / training model

1. **Identify the model**: Get `model_id` (from a deployment's champion model, or from training)
2. **Compute the insight**: Use the unified Insights API — `ShapMatrix.create(entity_id=model_id, source="validation")`
3. **Read the values**: Use `ShapMatrix.get_as_dataframe(model_id)`, or read `.matrix` / `.columns` / `.base_value`

**Example**: "Explain why the model predicted 0.85 for this customer record"

> **API note**: This skill uses the unified `datarobot.insights` API (SDK 3.x+), which is the
> preferred way to compute and retrieve model insights. Every insight class shares the same
> `create` / `compute` / `get` / `list` methods keyed on an `entity_id` (the model ID). The older
> per-resource methods (`model.get_roc_curve`, `model.get_confusion_matrix`,
> `model.get_lift_chart`, `dr.PredictionExplanations`) are legacy and should not be used for new
> work. For **deployment-time, per-row** prediction explanations returned alongside scoring, use
> the `datarobot-predictions` skill instead.

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

Model insights live in the unified `datarobot.insights` module. Import the class you need and
call `create` (compute + wait + return) or `get` (retrieve a previously computed insight). All
classes are keyed on `entity_id` (the model ID) and accept `source` (`"validation"`,
`"crossValidation"`, `"holdout"`, `"training"`) plus optional `data_slice_id`.

```python
from datarobot.insights import (
    ShapMatrix, ShapImpact, RocCurve, ConfusionMatrix, LiftChart,
)
```

**Prediction explanations (SHAP)**:
- `ShapMatrix.create(entity_id=model_id, source="validation")` - Compute per-row SHAP values
- `ShapMatrix.get_as_dataframe(model_id)` - SHAP matrix as a pandas DataFrame
- `.matrix`, `.columns`, `.base_value` - Raw SHAP values, feature names, and baseline

**Model diagnostics**:
- `RocCurve.create(entity_id=model_id, source="validation")` - `.auc`, `.roc_points`
- `ConfusionMatrix.create(entity_id=model_id, source="validation")` - `.confusion_matrix_data`, `.global_metrics`
- `LiftChart.create(entity_id=model_id, source="validation")` - `.bins`

**Feature importance**:
- `ShapImpact.create(entity_id=model_id, source="training")` - `.shap_impacts` (SHAP-based global importance)
- `model.get_or_request_feature_impact()` - Permutation-based feature impact (remains a `Model` method)

**Feature analysis**:
- `dr.FeatureEffects` / `model.get_or_request_feature_effects(source)` - Partial dependence / feature effects (remains a `Model` method; not part of the insights module)

See the [Common Patterns](#common-patterns) section below for complete examples.

## Best practices

1. **Use SHAP for local explanations**: SHAP values provide the best local (per-prediction) explanations
2. **Combine with global insights**: Use feature importance for global understanding, SHAP for local
3. **Explain in context**: Always explain predictions in the context of the business problem
4. **Visualize explanations**: Use charts and graphs to make explanations more understandable
5. **Document explanations**: Save explanations for compliance and auditing purposes
6. **Compare across models**: Use explainability to compare different models

## Common patterns

### Pattern 1: Get SHAP prediction explanations (Insights API)

```python
import datarobot as dr
from datarobot.insights import ShapMatrix
import os

# Initialize client
client = dr.Client(
    token=os.getenv("DATAROBOT_API_TOKEN"),
    endpoint=os.getenv("DATAROBOT_ENDPOINT")
)

model_id = "model_id_here"

# create() computes the insight and blocks until it's ready (use compute() for async).
shap = ShapMatrix.create(entity_id=model_id, source="validation")

# Per-row SHAP values as a DataFrame (rows = scored records, columns = features)
df = ShapMatrix.get_as_dataframe(model_id)
print(df.head())

# Or work with the raw values
print("Baseline (base value):", shap.base_value)
print("Features:", shap.columns)
print("First row SHAP values:", shap.matrix[0])
```

> SHAP-based explanations require a model that supports SHAP. If `create` reports the insight is
> unavailable, fall back to XEMP via the deployment scoring path (`datarobot-predictions` skill)
> or the legacy `dr.PredictionExplanations` API.

### Pattern 2: Generate model diagnostics (Insights API)

```python
import datarobot as dr
from datarobot.insights import RocCurve, ConfusionMatrix, LiftChart

model_id = "xyz123"

# ROC curve + AUC
roc = RocCurve.create(entity_id=model_id, source="validation")
print(f"AUC Score: {roc.auc:.3f}")
# roc.roc_points is a list of {falsePositiveRate, truePositiveRate, threshold, ...} dicts
best = max(roc.roc_points, key=lambda p: p["truePositiveRate"] - p["falsePositiveRate"])
print(f"Best threshold (Youden's J): {best['threshold']:.3f}")

# Confusion matrix (classification models)
cm = ConfusionMatrix.create(entity_id=model_id, source="validation")
print("Classes:", cm.columns)
print("Matrix:", cm.confusion_matrix_data)
print("Global metrics:", cm.global_metrics)

# Lift chart
lift = LiftChart.create(entity_id=model_id, source="validation")
print(f"Number of bins: {len(lift.bins)}")
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
- [DataRobot Insights API Reference](https://datarobot-public-api-client.readthedocs-hosted.com/en/latest/autodoc/api_reference.html#insights) (`datarobot.insights`)
- [DataRobot Model Insights Documentation](https://docs.datarobot.com/en/docs/modeling/analyze-models/index.html)
- [SHAP Documentation](https://shap.readthedocs.io/)

