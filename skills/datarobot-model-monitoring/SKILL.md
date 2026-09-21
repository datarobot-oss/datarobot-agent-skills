---
name: datarobot-model-monitoring
description: Tools and guidance for monitoring model performance, tracking data drift, managing model health, and detecting prediction anomalies. Use when monitoring deployed models, tracking drift, or investigating prediction anomalies.
---

# DataRobot Model Monitoring Skill

This skill provides comprehensive guidance for monitoring deployed models, tracking performance metrics, detecting data drift, and managing model health.

## Quick Start

**Most common use case**: Check deployment health and data drift

1. **Check service stats**: `deployment.get_service_stats(...)` to review prediction volume/latency
2. **Check drift**: `deployment.get_feature_drift(...)` / `deployment.get_target_drift(...)`
3. **Compare over time**: Use `get_service_stats_over_time(...)` and drift periods to assess trends.
   Each element of `.buckets` is a dict with keys `period`, `model_id`, `value` — the metric value is under `"value"`,
   e.g. `total = sum(b["value"] or 0 for b in sot.buckets)`

**Example**: "Check the health of deployment abc123 and report any data drift issues"

## When to use this skill

Use this skill when you need to:
- Monitor model performance in production
- Track data drift and feature drift
- Detect prediction anomalies
- Monitor prediction accuracy over time
- Set up alerts for model degradation
- Analyze model health metrics
- Compare production performance to training performance

## Key capabilities

### 1. Performance Monitoring

- Track prediction accuracy and metrics over time
- Compare production metrics to training metrics
- Monitor prediction volume and latency
- Identify performance degradation trends

### 2. Data Drift Detection

- Detect changes in feature distributions
- Identify feature drift (statistical changes)
- Monitor target drift (if actuals available)
- Alert on significant drift events

### 3. Prediction Monitoring

- Monitor prediction distributions
- Detect prediction anomalies
- Track prediction confidence scores
- Identify unusual prediction patterns

### 4. Health Management

- Assess overall model health
- Generate monitoring reports
- Set up automated alerts
- Manage model retraining triggers

## Workflow examples

### Example 1: Check model health and drift

**User request**: "Check the health of deployment abc123 and report any data drift issues."

**Agent workflow**:
1. Get deployment monitoring status
2. Retrieve recent performance metrics
3. Check for data drift in key features
4. Compare current metrics to baseline (training)
5. Identify any significant drift or degradation
6. Report findings with recommendations

### Example 2: Set up drift monitoring alerts

**User request**: "Set up alerts for deployment xyz789 to notify when feature drift exceeds 0.2."

**Agent workflow**:
1. Get deployment configuration
2. Configure drift threshold (0.2)
3. Set up alert notifications
4. Specify which features to monitor
5. Test alert configuration
6. Confirm monitoring is active

## Using DataRobot SDK

This skill guides you to use the DataRobot Python SDK directly. Install the SDK if needed:

```bash
uv pip install datarobot || python -m pip install datarobot
```

### Key SDK Operations

Use these DataRobot SDK and MLOps API methods for monitoring:

**Deployment Monitoring**:
- `deployment.get_service_stats(...)` - Get service statistics (latency, volume, etc.)
- `deployment.get_feature_drift(...)` - Get feature drift metrics (returns `FeatureDrift` objects)
- `deployment.get_target_drift(...)` - Get target drift metrics (returns `TargetDrift`)
  - **SDK bug (still present in 3.19.0)**: on unsegmented deployments this raises `DataError: {'segment_value': 'is required'}`. Workaround — call the REST endpoint directly:
    `data = dr.Client().get(f"deployments/{deployment_id}/targetDrift/", params={"start": start_iso, "end": end_iso}).json()` — `start`/`end` are optional (default: last 7 days) and take hour-aligned ISO-8601 timestamps (`startTime`/`endTime` are rejected with 400); then read camelCase keys `data["driftScore"]`, `data["targetName"]`, `data["sampleSize"]`
- `deployment.get_prediction_results(...)` - Retrieve recorded prediction results (if enabled)

**Note**: Monitoring endpoints reject `start_time`/`end_time` not aligned to the top of an hour (HTTP 400).
Truncate `end_time` *forward* to the top of the next hour — truncating back silently drops the in-progress
hour's traffic (reports 0 predictions), and the API accepts a future `end_time`:
`end_time = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)`.

**Model Performance**:
- `model.metrics` - Model performance metrics (dict of `{metric: {partition: score}}`)
- `datarobot.insights.RocCurve.get(model_id, source="validation")` - Get ROC curve for comparison (`source`: `"validation"`, `"crossValidation"`, or `"holdout"`; the older `model.get_roc_curve(source)` is deprecated and warns)

**Note**: Some monitoring features may require DataRobot MLOps API. See the [Common Patterns](#common-patterns) section below for examples.

## Best practices

1. **Regular monitoring**: Check model health regularly, not just when issues arise
2. **Baseline comparison**: Always compare production metrics to training baseline
3. **Drift thresholds**: Set appropriate drift thresholds based on your domain
4. **Key features**: Focus monitoring on high-importance features
5. **Automated alerts**: Set up alerts for critical issues
6. **Historical analysis**: Track trends over time, not just point-in-time metrics

## Common patterns

### Pattern 1: Health check
```python
import datarobot as dr

# Initialize client
dr.Client()

# Get deployment
deployment = dr.Deployment.get("abc123")

# Get service stats (requires MLOps monitoring to be enabled)
# ServiceStats exposes values via the .metrics dict, not as attributes.
stats = deployment.get_service_stats()
print(f"Prediction count: {stats.metrics['totalPredictions']}")
print(f"Median response time (ms): {stats.metrics['responseTime']}")  # p50 by default; adjust via response_time_quantile

# Get recorded prediction results (if available / enabled)
try:
    recent = deployment.get_prediction_results(limit=10)
    print(f"Recent prediction results: {len(recent)}")
except Exception as e:
    print(f"Prediction results not available: {e}")
```

### Pattern 2: Drift detection
```python
import datarobot as dr

# Get deployment
deployment = dr.Deployment.get("abc123")

# Get feature drift (requires MLOps monitoring)
try:
    drifts = deployment.get_feature_drift()
    # 0.15/0.3 are the documented medium/high thresholds (see Alert thresholds below)
    high = [d for d in drifts if (d.drift_score or 0) > 0.15]
    print(f"Features with drift_score > 0.15: {len(high)}")
    for d in high[:10]:
        print(f"{d.name}: {d.drift_score}")
except Exception as e:
    print(f"Feature drift requires MLOps monitoring: {e}")
```

## Monitoring metrics

### Performance Metrics
- **Accuracy**: Prediction accuracy (classification)
- **RMSE/MAE**: Prediction error (regression)
- **AUC**: Model discrimination (classification)
- **Prediction volume**: Number of predictions made

### Drift Metrics
- **Feature drift**: Statistical changes in feature distributions
- **Target drift**: Changes in target distribution (if available)
- **Prediction drift**: Changes in prediction distributions
- **Drift score**: Overall drift severity (0-1 scale)

## Alert thresholds

Recommended thresholds:

- **High drift**: > 0.3 (significant changes, investigate immediately)
- **Medium drift**: 0.15-0.3 (moderate changes, monitor closely)
- **Low drift**: < 0.15 (minor changes, normal variation)

Adjust thresholds based on your domain and use case sensitivity.

## Model health status

- **Healthy**: Performance within expected range, minimal drift
- **Degrading**: Performance declining, some drift detected
- **Unhealthy**: Significant performance issues or high drift
- **Unknown**: Insufficient data for assessment

## Error handling

Common errors and solutions:

- **Insufficient data**: Need minimum prediction volume for monitoring
- **Baseline unavailable**: Ensure training baseline is available
- **Access issues**: Verify deployment permissions and access

## SDK Setup

### Install DataRobot SDK

```bash
uv pip install datarobot || python -m pip install datarobot
```

### Initialize Client

```python
import datarobot as dr

dr.Client()
```

**Note**: Some monitoring features require DataRobot MLOps API access. Check your DataRobot plan for MLOps availability.

## Resources

- [DataRobot Python SDK Documentation](https://datarobot-public-api-client.readthedocs-hosted.com/)
- [DataRobot Model Monitoring Documentation](https://docs.datarobot.com/en/docs/mlops/monitor/index.html)

