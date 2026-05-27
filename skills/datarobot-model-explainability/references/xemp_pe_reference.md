# XEMP Prediction Explanations Reference

Parameter reference for `dr.PredictionExplanations` and related classes.
SDK version: `datarobot>=2.26` (XEMP API is stable; `datarobot.insights` SHAP API is preferred for new code).

Source: https://datarobot-public-api-client.readthedocs-hosted.com/en/latest-release/reference/modeling/insights/prediction_explanations.html

---

## When to use XEMP vs SHAP

| Situation | Use |
|-----------|-----|
| Default / new code | `ShapMatrix` / `ShapPreview` from `datarobot.insights` |
| Anomaly-detection models with >1000 features | XEMP PE if SHAP is unavailable |
| Regulatory requirement for XEMP | XEMP PE |
| Feature Impact methodology required | XEMP PE |

---

## Prerequisites

All must be satisfied before calling `PredictionExplanations.create()`:

1. **Feature Impact computed**:
   ```python
   job = model.request_feature_impact()
   job.wait_for_completion()
   ```

2. **PredictionExplanationsInitialization created** (one-time per model):
   ```python
   dr.PredictionExplanationsInitialization.create(project_id=project_id, model_id=model_id)
   ```

3. **Scoring dataset uploaded** to the AI Catalog (`dataset_id` passed to `.create()`).

---

## PredictionExplanationsInitialization

### `PredictionExplanationsInitialization.create(project_id, model_id)`

One-time initialization. Safe to call multiple times; check first with `.get()`.

### `PredictionExplanationsInitialization.get(project_id, model_id)`

Check whether initialization exists. Raises `ClientError` if not found.

### `PredictionExplanationsInitialization.delete(project_id, model_id)`

Delete initialization (forces re-initialization on next `.create()`).

---

## PredictionExplanations

### `PredictionExplanations.create(project_id, model_id, dataset_id, ...)`

Submit an async job to compute explanations on a dataset. Call
`pe_job.get_result_when_complete()` to retrieve the `PredictionExplanations` result.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_id` | str | required | DataRobot project ID |
| `model_id` | str | required | DataRobot model ID |
| `dataset_id` | str | required | AI Catalog dataset ID to explain |
| `max_explanations` | int | 3 | Top-N feature explanations per row; at most 50 can be returned |
| `threshold_high` | float | None | Only explain rows with prediction >= this |
| `threshold_low` | float | None | Only explain rows with prediction <= this |
| `mode` | `TopPredictionsMode` or `ClassListMode` | predicted class only | For multiclass/clustering: which classes to explain |

### `PredictionExplanations.create_on_training_data(project_id, model_id, ...)`

Same as `.create()` but runs on the model's training data instead of an uploaded dataset.

### `PredictionExplanations.get(project_id, prediction_explanations_id)`

Retrieve a computed PE object by ID.

### `PredictionExplanations.list(project_id, model_id=None)`

List all PE objects for a project (optionally filtered by model).

### Methods on PE result object

| Method | Returns | Description |
|--------|---------|-------------|
| `.get_rows(batch_size=None)` | iterator | Iterate explanation rows |
| `.get_all_as_dataframe(exclude_adjusted_predictions=True)` | `pd.DataFrame` | All rows as DataFrame |
| `.download_to_csv(filename, exclude_adjusted_predictions=True)` | None | Write to CSV |
| `.is_multiclass()` | bool | Whether this is a multiclass explanation |

---

## Explanation row structure

Each row from `.get_rows()` has:

| Field | Type | Description |
|-------|------|-------------|
| `row_index` | int | Position in dataset |
| `prediction` | float | Model's prediction for this row |
| `adjusted_prediction` | float | Exposure-adjusted prediction (if applicable) |
| `prediction_explanations` | list[dict] | Feature explanations |

Each entry in `prediction_explanations`:

```python
{
    "feature": "income",         # feature name
    "featureValue": "85000",     # actual value of the feature
    "strength": 0.18,            # XEMP contribution (positive = increases prediction)
    "label": "income",           # display label
    "qualitative_strength": "++" # qualitative indicator
}
```

---

## Adjusted predictions (exposure projects)

For insurance or other exposure-normalized projects:

```python
df = pe_obj.get_all_as_dataframe(exclude_adjusted_predictions=False)
# DataFrame now includes 'adjusted_prediction' column
```

---

## Multiclass / clustering

```python
pe_job = dr.PredictionExplanations.create(
    project_id=project_id,
    model_id=model_id,
    dataset_id=dataset.id,
    mode=dr.models.ClassListMode(["class_a", "class_b"]),  # specify which classes to explain
)

# Check if multiclass
pe_obj = pe_job.get_result_when_complete()
print(pe_obj.is_multiclass())
```

---

## Notes

- `max_explanations` can return at most 50 explanations because XEMP computes explanations for
  the global top 50 features
- `threshold_high` and `threshold_low` can be combined to explain only extreme predictions
- XEMP explanations use the XEMP methodology (not SHAP); magnitudes are not comparable across models
- For SHAP-based explanations, prefer `datarobot.insights.ShapMatrix` / `ShapPreview` with
  `entity_id=model_id`. Export via `pd.DataFrame(result.matrix, columns=result.columns)` or
  `ShapMatrix.get_as_dataframe(entity_id=..., source=...)` — not legacy `datarobot.models.ShapMatrix`.
