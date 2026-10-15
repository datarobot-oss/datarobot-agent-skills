# Generic `dr_otel_config.py` Template

This is the core `configure_otel()` function to generate for every project, regardless of framework. Framework-specific files in `frameworks/` layer additional setup (auto-instrumentors, callbacks) on top of this.

**Critical rules (also summarized in SKILL.md):**
1. Always pass `endpoint=` and `headers=` directly to exporters — NEVER use `OTEL_EXPORTER_OTLP_*` env vars (some frameworks detect these and create conflicting providers)
2. Be additive — add DataRobot as an additional span processor to any existing TracerProvider, don't replace it
3. Use `SimpleSpanProcessor` (not Batch) to avoid flush-before-shutdown issues
4. Use DELTA temporality for metrics (required by DataRobot)
5. Set the `Resource` `service.name` to `DATAROBOT_ENTITY_ID` — DataRobot files a trace under the entity named by `service.name` (parsed as `<entity_type>-<entity_id>`), so a default/app service name silently drops the trace from the UI even though the upload returns 200/202

The `DATAROBOT_ENTITY_ID` at runtime is the Use Case entity (`experiment_container-<use_case_id>`) by default, a deployment entity (`deployment-<id>`) if a shell deployment was used instead, or a **workload** entity (`workload-<workload_id>`) when the agent runs as a DataRobot Workload (the platform injects `WORKLOAD_ID`, so use `workload-${WORKLOAD_ID}`).

## Template

```python
"""DataRobot OpenTelemetry configuration.

Configures traces, logs, and metrics export to DataRobot's OTel endpoint.
Call configure_otel() at application startup, before any agent code runs.

Required env vars at runtime:
    DATAROBOT_API_TOKEN      - DataRobot API key
    DATAROBOT_ENTITY_ID      - experiment_container-<use_case_id> (or deployment-<deployment_id>)
    DATAROBOT_OTEL_ENDPOINT  - https://<your-instance>.datarobot.com/otel
"""

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import (
    Counter,
    Histogram,
    MeterProvider,
    ObservableCounter,
)
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


def _build_dr_headers():
    """Build DataRobot authentication headers for OTel exporters."""
    api_key = os.environ.get("DATAROBOT_API_TOKEN", "")
    entity_id = os.environ.get("DATAROBOT_ENTITY_ID", "")
    if not api_key:
        logging.warning(
            "DATAROBOT_API_TOKEN not set — OTel export to DataRobot will fail"
        )
    if not entity_id:
        logging.warning(
            "DATAROBOT_ENTITY_ID not set — OTel export to DataRobot will fail"
        )
    return {
        "X-DataRobot-Entity-Id": entity_id,
        "X-DataRobot-Api-Key": api_key,
    }


def _get_endpoint():
    """Get DataRobot OTel endpoint, auto-deriving from DATAROBOT_ENDPOINT if needed."""
    endpoint = os.environ.get("DATAROBOT_OTEL_ENDPOINT", "")
    if endpoint:
        return endpoint.rstrip("/")
    # Auto-derive from DATAROBOT_ENDPOINT (e.g. https://app.datarobot.com/api/v2 → .../otel)
    api_endpoint = os.environ.get("DATAROBOT_ENDPOINT", "")
    if api_endpoint:
        base = api_endpoint.rstrip("/")
        if base.endswith("/api/v2"):
            base = base[: -len("/api/v2")]
        return f"{base}/otel"
    return ""


def configure_otel():
    """Configure OpenTelemetry to export traces, logs, and metrics to DataRobot.

    This function is additive — it adds DataRobot as an additional exporter
    alongside any existing OTel setup. It does not replace existing providers.
    """
    headers = _build_dr_headers()
    endpoint = _get_endpoint()
    if not endpoint:
        logging.warning("DATAROBOT_OTEL_ENDPOINT not set — skipping OTel configuration")
        return
    # DataRobot files each trace under the entity named by the span's
    # service.name, parsed as "<entity_type>-<entity_id>". It MUST equal
    # DATAROBOT_ENTITY_ID (e.g. "experiment_container-<id>", "deployment-<id>",
    # or "workload-<id>") -- otherwise spans upload fine (200/202) but never
    # appear in the UI. The entity header alone is not enough; the tracing UI
    # filters on service.name.
    entity_id = os.environ.get("DATAROBOT_ENTITY_ID", "")
    resource = Resource.create({"service.name": entity_id} if entity_id else {})

    # --- Traces ---
    dr_span_processor = SimpleSpanProcessor(
        OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers)
    )
    existing_provider = trace.get_tracer_provider()
    if hasattr(existing_provider, "add_span_processor"):
        # A provider already exists, so ITS resource -- not the one built above --
        # stamps service.name on every span, including the ones this processor
        # exports to DataRobot. An existing provider's resource can't be rewritten
        # here, and DataRobot attributes a trace by its service.name, so unless
        # that provider was created with service.name == DATAROBOT_ENTITY_ID the
        # spans upload fine but never appear. The fix is ordering: call
        # configure_otel() BEFORE the framework creates its provider (so the
        # else-branch below runs and sets the resource), or create that provider
        # with service.name set to the entity id. Warn loudly when it's wrong.
        existing_name = getattr(
            getattr(existing_provider, "resource", None), "attributes", {}
        ).get("service.name")
        if entity_id and existing_name != entity_id:
            logging.warning(
                "OTel TracerProvider already exists with service.name=%r, but "
                "DataRobot needs service.name=%r to attribute these traces. Call "
                "configure_otel() before the framework initializes, or create the "
                "provider with service.name set to DATAROBOT_ENTITY_ID.",
                existing_name,
                entity_id,
            )
        existing_provider.add_span_processor(dr_span_processor)
    else:
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(dr_span_processor)
        trace.set_tracer_provider(provider)

    # --- Logs ---
    log_exporter = OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers)
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    # Custom formatter ensures OTLP log bodies are never empty
    # (some libraries emit records with empty getMessage())
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)

    # --- Metrics ---
    preferred_temporality = {
        Counter: AggregationTemporality.DELTA,
        Histogram: AggregationTemporality.DELTA,
        ObservableCounter: AggregationTemporality.DELTA,
    }
    metric_exporter = OTLPMetricExporter(
        endpoint=f"{endpoint}/v1/metrics",
        headers=headers,
        preferred_temporality=preferred_temporality,
    )
    meter_provider = MeterProvider(
        metric_readers=[PeriodicExportingMetricReader(metric_exporter)],
        resource=resource,
    )
    metrics.set_meter_provider(meter_provider)
```

## OTel provider initialization order warning

Some frameworks override the global TracerProvider at startup (notably Google ADK). When this happens, the standard trace setup above will lose the DataRobot exporter. The framework reference files document which frameworks have this issue and provide alternative patterns (e.g., lazy injection via callbacks). Always check the framework reference file.

Existing OTel setups (e.g., exporters to Jaeger, Datadog, Google Cloud Trace) are preserved when possible — DataRobot is added alongside, not replacing. However, note that OTel has a single global provider per signal. Whoever calls `set_tracer_provider()` last wins. The additive pattern above avoids calling `set_tracer_provider()` when a provider already exists, instead adding a processor to the existing one.
