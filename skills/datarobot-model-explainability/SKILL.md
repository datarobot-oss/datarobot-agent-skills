---
name: datarobot-model-explainability
description: >
  Tools and guidance for model explainability, prediction explanations, feature impact analysis,
  SHAP values, SHAP distributions, anomaly assessment, and model diagnostics. Use when analyzing
  model explanations, feature impact, SHAP values, SHAP distributions, anomaly assessment, or
  diagnosing model behavior.
---

# DataRobot Model Explainability Skill

This skill covers SHAP insights, XEMP prediction explanations, anomaly explanations, and model diagnostics.

> **SDK version**: Use `datarobot>=3.6.0` for the full API set in this skill (`ShapDistributions`
> was added in 3.6; `ShapMatrix`, `ShapImpact`, and `ShapPreview` are available in
> `datarobot>=3.4.0`). Use `from datarobot.insights import ShapMatrix, ...` with
> `entity_id=model_id` — not legacy `datarobot.models.ShapMatrix` (`project_id` / `dataset_id`).
> `ShapMatrix`, `ShapImpact`, `ShapPreview`, and `ShapDistributions` are the canonical SHAP API.
> The older `dr.PredictionExplanations` (XEMP-based) remains available but is the secondary path.

---

## Quick Start

| Goal | API to use | Prerequisites |
|------|-----------|---------------|
| SHAP values for all features, all rows | `ShapMatrix.create(entity_id=model_id)` | None - universal SHAP |
| Per-row top-feature explanations | `ShapPreview.create(entity_id=model_id)` | None |
| Aggregated feature importance via SHAP | `ShapImpact.create(entity_id=model_id)` | None |
| SHAP value distributions across features | `ShapDistributions.create(entity_id=model_id)` | None |
| SHAP for a filtered segment | `dr.DataSlice.create(...)` + `ShapMatrix.create(..., data_slice_id=...)` | Data slice definition |
| XEMP-based prediction explanations | `dr.PredictionExplanations.create(...)` | Feature Impact; PE initialization; dataset uploaded |
| Anomaly explanations (time series) | `AnomalyAssessmentRecord.compute(project_id, model_id, ...)` | Anomaly model |
| ROC / lift / confusion (insights) | `RocCurve.create(...)` / `LiftChart.create(...)` / `ConfusionMatrix.create(...)` | Validation data |
| ROC / lift / confusion (Model helpers) | `model.get_roc_curve()` / `model.get_lift_chart()` / `model.get_confusion_chart()` | Validation data |

**Universal SHAP is the preferred path** - no dataset pre-upload or Feature Impact step required.

## When to use this skill

Use this skill when you need to explain leaderboard model behavior, compute SHAP insights, use
XEMP prediction explanations, analyze anomaly explanations, or retrieve model diagnostics.

## Key capabilities

### 1. SHAP insights

- Compute `ShapMatrix`, `ShapPreview`, `ShapImpact`, and `ShapDistributions`
- Filter insights with `dr.DataSlice`

### 2. XEMP and anomaly explanations

- Use XEMP `dr.PredictionExplanations` when specifically required
- Retrieve time series anomaly assessment records and explanations

### 3. Diagnostics

- Retrieve ROC, lift, and confusion insights
- Use Model helpers for ROC, lift, confusion, and feature effects

## Setup

```python
import os
import datarobot as dr
from datarobot.insights import ShapMatrix, ShapImpact, ShapPreview, ShapDistributions

dr.Client(
    token=os.environ["DATAROBOT_API_TOKEN"],
    endpoint=os.environ.get("DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2"),
)
```

---

## Core API: `datarobot.insights`

```python
import pandas as pd
from datarobot.insights import ShapMatrix, ShapImpact, ShapPreview, ShapDistributions

model_id = "YOUR_MODEL_ID"

matrix = ShapMatrix.create(entity_id=model_id)
df = pd.DataFrame(matrix.matrix, columns=matrix.columns)

impact = ShapImpact.create(entity_id=model_id)
preview = ShapPreview.create(entity_id=model_id)
distributions = ShapDistributions.create(entity_id=model_id)
```

Use `ShapMatrix` for full row-by-feature SHAP values, `ShapPreview` for compact top-driver rows,
`ShapImpact` for aggregated SHAP importance, and `ShapDistributions` for per-feature SHAP
distributions. Use `source="externalTestSet"` plus `external_dataset_id` for external datasets.
See `references/shap_api_reference.md` for parameters, exports, and limitations.

---

## Secondary path: XEMP Prediction Explanations

Use `dr.PredictionExplanations` when XEMP explanations are specifically required (e.g., certain
regulatory contexts, or when SHAP is unavailable for the model type).

**Prerequisites** (all required before calling `.create()`):
1. Feature Impact must be computed: `model.request_feature_impact()` and wait
2. Prediction explanations initialized: `dr.PredictionExplanationsInitialization.create(...)`
3. Scoring dataset uploaded to the AI Catalog

```python
import datarobot as dr

model = dr.Model.get(project=project_id, model_id=model_id)
model.request_feature_impact().wait_for_completion()
dr.PredictionExplanationsInitialization.create(project_id=project_id, model_id=model_id)

dataset = dr.Dataset.upload("./data/scoring_data.csv")
pe_job = dr.PredictionExplanations.create(
    project_id=project_id,
    model_id=model_id,
    dataset_id=dataset.id,
    max_explanations=5,      # top N features per row, up to 50
    threshold_high=0.5,      # only explain rows with prediction >= threshold
    threshold_low=0.1,       # only explain rows with prediction <= threshold
)

pe_obj = pe_job.get_result_when_complete()
```

Use `pe_obj.get_rows()`, `pe_obj.get_all_as_dataframe()`, or `pe_obj.download_to_csv(...)` to
retrieve results. For parameters, multiclass modes, and exposure-adjusted predictions, see
`references/xemp_pe_reference.md`.

## Data slices for filtered insights

Use `dr.DataSlice` when the user asks to explain model behavior for a segment, such as a
region, product line, target class, or high-risk cohort. Pass the resulting `data_slice_id` into
the `datarobot.insights` SHAP APIs.

```python
import datarobot as dr
from datarobot.insights import ShapMatrix

data_slice = dr.DataSlice.create(
    name="high_income_customers",
    filters=[{"operand": "income", "operator": ">", "values": 100000}],
    project=project_id,
)

shap_matrix = ShapMatrix.create(
    entity_id=model_id,
    source="validation",
    data_slice_id=data_slice.id,
)
```

---

## Anomaly assessment (time series models)

For time series anomaly detection models, use `AnomalyAssessmentRecord`.

```python
from datarobot.models.anomaly_assessment import AnomalyAssessmentRecord

record = AnomalyAssessmentRecord.compute(
    project_id=project_id,
    model_id=model_id,
    backtest=0,           # backtest index (int) or "holdout"
    source="validation",  # "training" or "validation" only
    series_id=None,       # required for multiseries projects
)

records = AnomalyAssessmentRecord.list(project_id=project_id, model_id=model_id)
latest = record.get_latest_explanations()

regions = record.get_predictions_preview().find_anomalous_regions()
explanations = record.get_explanations_data_in_regions(regions=regions)

ranged = record.get_explanations(
    start_date="2024-01-01T00:00:00.000000Z",
    end_date="2024-06-01T00:00:00.000000Z",
)
```

---

## Model diagnostics

Use the same `entity_id=model_id` pattern as SHAP insights. `FeatureEffects` / partial dependence
is still retrieved through Model helpers (not in `datarobot.insights`).

### Insights diagnostics (preferred — matches SHAP API)

```python
from datarobot.insights import RocCurve, LiftChart, ConfusionMatrix

roc = RocCurve.create(entity_id=model_id)
lift = LiftChart.create(entity_id=model_id)
confusion = ConfusionMatrix.create(entity_id=model_id)
```

### Model helpers (alternative)

```python
model = dr.Model.get(project=project_id, model_id=model_id)

roc = model.get_roc_curve(source="validation")
lift = model.get_lift_chart(source="validation")
confusion = model.get_confusion_chart(source="validation")

# Feature Impact (non-SHAP) and Feature Effects (partial dependence for top features)
fi = model.get_feature_impact()
feature_effects = model.get_feature_effect(source="validation")
```

---

## Interpreting SHAP values

- **Positive value**: feature pushes prediction higher than baseline
- **Negative value**: feature pushes prediction lower than baseline
- **Magnitude**: size of influence; larger absolute value = stronger effect
- **Sum**: all SHAP values for a row sum to `prediction - base_value` in the link-function space
- **`base_value`**: the model's mean prediction (the "no information" baseline)

Example: if `base_value = 0.35` and a row's prediction is `0.72`, the row's SHAP values sum to
`0.37` when `link_function = "identity"`. A feature with SHAP `+0.20` contributed 20 units in
that same link-function space above baseline.

When `link_function = "logit"`, SHAP values are in log-odds space. Add feature contributions to
`base_value` in log-odds space, then use inverse-logit (`scipy.special.expit`) on the resulting
total to convert it to a probability. Do not apply `expit` to individual SHAP values as if they
were probability deltas.

---

## Decision guide

```
Task: explain predictions
    |
    - Need all features + all rows?     -> ShapMatrix.create(entity_id=model_id)
    - Need top-N features per row?      -> ShapPreview.create(entity_id=model_id)
    - Need aggregated importance?       -> ShapImpact.compute(entity_id=model_id)
    - Need feature SHAP distributions?  -> ShapDistributions.create(entity_id=model_id)
    - Need a segment/cohort only?       -> dr.DataSlice + data_slice_id
    - XEMP required (regulatory/type)?  -> dr.PredictionExplanations.create(...)
    - Time series / anomaly model?      -> AnomalyAssessmentRecord.compute(project_id, model_id, ...)
```

---

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `SHAP not available for this model` | Unsupported model type, or anomaly-detection model with >1000 features | Check model support; use XEMP PE if SHAP is unavailable |
| `Feature Impact not computed` | PredictionExplanations prerequisite missing | Run `model.request_feature_impact()` and wait |
| Missing `PredictionExplanationsInitialization` | PE not initialized | Call `PredictionExplanationsInitialization.create()` |
| `source='holdout'` fails | Holdout not unlocked | Unlock holdout in project settings first |
| Empty `previews` | No rows in partition | Check partition contains data |

---

## Reference files

- `references/shap_api_reference.md` - full parameter signatures for ShapMatrix, ShapImpact, ShapPreview, ShapDistributions
- `references/xemp_pe_reference.md` - PredictionExplanations and PredictionExplanationsInitialization parameter reference
- `scripts/compute_shap_matrix.py` - compute and export ShapMatrix to CSV or DataFrame

## Resources

- [datarobot.insights API reference](https://datarobot-public-api-client.readthedocs-hosted.com/en/latest-release/insights.html)
- [Prediction Explanations user guide](https://datarobot-public-api-client.readthedocs-hosted.com/en/latest-release/reference/modeling/insights/prediction_explanations.html)
