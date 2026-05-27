# SHAP API Reference

Full parameter signatures for `datarobot.insights` classes.
SDK version: `datarobot>=3.4.0` (latest-release: 3.10.0rc0)

Source: https://datarobot-public-api-client.readthedocs-hosted.com/en/latest-release/insights.html

---

## Import

```python
from datarobot.insights import ShapMatrix, ShapImpact, ShapPreview, ShapDistributions
```

---

## ShapMatrix

Raw SHAP values for each feature column and each row.

### `ShapMatrix.create(entity_id, source='validation', **kwargs)`

Blocking call - computes and returns a ShapMatrix.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity_id` | str | required | Model ID |
| `source` | str | `'validation'` | Partition: `'validation'`, `'crossValidation'`, `'holdout'`, `'externalTestSet'` |
| `data_slice_id` | str | None | Optional Data Slice ID to filter the selected partition |
| `external_dataset_id` | str | None | Dataset ID from AI Catalog; required when `source='externalTestSet'` |
| `quick_compute` | bool | None | If true/unspecified, compute on a 2500-row sample; if false, compute all rows |

### `ShapMatrix.compute(entity_id, source='validation', **kwargs)`

Non-blocking - returns a job reference.

Same parameters as `.create()`. Call `job.get_result_when_complete()` to wait.

### `ShapMatrix.get(entity_id, source)`

Retrieve an already-computed ShapMatrix by model + partition.

### `ShapMatrix.list(entity_id)`

List all computed ShapMatrix objects for a model (one per partition computed).

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `matrix` | list[list[float]] | 2D array: rows x features |
| `columns` | list[str] | Feature names (same order as matrix columns) |
| `base_value` | float | Model's mean prediction (baseline) |
| `link_function` | str | Link function: `'identity'` for regression, `'logit'` for binary classification |
| `source` | str | Partition this matrix was computed on |

### Methods on result

| Method | Returns | Description |
|--------|---------|-------------|
| `.get_as_dataframe()` | `pd.DataFrame` | ShapMatrix as pandas DataFrame |
| `.get_as_csv()` | str | ShapMatrix as CSV string |
| `.get_uri()` | str | URI of the stored matrix |
| `.open_in_browser()` | None | Open result in browser |
| `.sort()` | ShapMatrix | Return sorted copy |

### Notes

- Not available for blenders
- Not available for models with >1000 features
- Universal SHAP (permutation-based) works on any other supported model without prerequisites
- Model-specific SHAP (tree/kernel explainer) available for select model types
- When `link_function='logit'`, values are in log-odds space; use `exp(shap)` for probability space

---

## ShapImpact

Aggregated feature importance based on SHAP matrix values.

### `ShapImpact.create(entity_id, source='training')`

Blocking call.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity_id` | str | required | Model ID |
| `source` | str | `'training'` | Currently only `'training'` is supported |
| `data_slice_id` | str | None | Optional Data Slice ID |
| `quick_compute` | bool | None | If true/unspecified, compute on a 2500-row sample; if false, compute all rows |

### `ShapImpact.compute(entity_id, source='training')`

Non-blocking. Returns job; call `job.get_result_when_complete()`.

### `ShapImpact.get(entity_id)` / `ShapImpact.list(entity_id)`

Retrieve existing ShapImpact results.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `shap_impacts` | list[list] | List of `[feature_name, normalized_impact, unnormalized_impact]` |
| `base_value` | float or list[float] | Baseline prediction value(s) |
| `row_count` | int | Number of rows used for computation |
| `capping` | bool | Whether extreme SHAP values were capped |
| `link` | str | Link function |

### Notes

- `normalized_impact`: impact scaled so features sum to 1.0
- `unnormalized_impact`: raw mean absolute SHAP value for the feature
- Results are sorted descending by importance

---

## ShapPreview

Per-row top-feature SHAP explanations in a compact "preview" format.

### `ShapPreview.create(entity_id, source='validation', **kwargs)`

Blocking.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity_id` | str | required | Model ID |
| `source` | str | `'validation'` | Partition: same options as ShapMatrix |
| `data_slice_id` | str | None | Optional Data Slice ID |
| `external_dataset_id` | str | None | Required when `source='externalTestSet'` |

### `ShapPreview.compute(entity_id, source='validation', **kwargs)`

Non-blocking variant.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `previews` | list[dict] | Per-row preview data (see structure below) |
| `previews_count` | int | Total number of rows |

### `previews` row structure

```python
{
    "row_index": 0,
    "prediction_value": 0.72,
    "preview_values": [
        {
            "feature_rank": 1,
            "feature_name": "income",
            "feature_value": "85000",
            "shap_value": 0.18,
            "has_text_explanations": False,
            "text_explanations": [],
        },
        # ... top-N features
    ]
}
```

---

## ShapDistributions

Distribution of SHAP values across rows for each feature.

### `ShapDistributions.create(entity_id, source='validation', data_slice_id=None, **kwargs)`

Blocking.

### `ShapDistributions.compute(entity_id, source='validation', data_slice_id=None, **kwargs)`

Non-blocking.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `features` | list[dict] | Per-feature distribution data |
| `total_features_count` | int | Total number of features |

---

## Constraints and limitations

| Constraint | Detail |
|-----------|--------|
| Blenders | SHAP not computed for blenders |
| Feature count | SHAP not available for >1000 features |
| ShapImpact source | Only `'training'` currently supported |
| Holdout | `source='holdout'` requires holdout to be unlocked in the project |
| Data slices | Use `dr.DataSlice.create()`, `.list()`, or `.get()`, then pass `data_slice_id` |
| Custom models | SHAP for custom models requires additional setup (see SHAP insights user guide) |
