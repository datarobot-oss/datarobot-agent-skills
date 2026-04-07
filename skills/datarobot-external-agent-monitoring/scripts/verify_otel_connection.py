#!/usr/bin/env python3
"""
Verify OTel connection to DataRobot by sending test telemetry.

Sends a test trace span, log record, and metric to DataRobot's OTel endpoint
to confirm the pipeline is working before deploying the instrumented agent.

Usage:
    python verify_otel_connection.py

Env vars:
    DATAROBOT_API_TOKEN      - DataRobot API token
    DATAROBOT_ENTITY_ID      - deployment-<deployment_id>
    DATAROBOT_OTEL_ENDPOINT  - https://<instance>.datarobot.com/otel
"""

import json
import logging
import os
import sys

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


def verify_connection() -> dict:
    """Send test telemetry to DataRobot and report results.

    Returns:
        Dict with status and per-signal results
    """
    api_key = os.environ.get("DATAROBOT_API_TOKEN", "")
    entity_id = os.environ.get("DATAROBOT_ENTITY_ID", "")
    endpoint = os.environ.get("DATAROBOT_OTEL_ENDPOINT", "")

    errors = []
    if not api_key:
        errors.append("DATAROBOT_API_TOKEN env var is required")
    if not entity_id:
        errors.append("DATAROBOT_ENTITY_ID env var is required")
    if not endpoint:
        errors.append("DATAROBOT_OTEL_ENDPOINT env var is required")
    if entity_id and not entity_id.startswith("deployment-"):
        errors.append(
            f"DATAROBOT_ENTITY_ID must start with 'deployment-', got: {entity_id}"
        )

    if errors:
        return {"status": "error", "errors": errors}

    headers = {
        "X-DataRobot-Entity-Id": entity_id,
        "X-DataRobot-Api-Key": api_key,
    }
    resource = Resource.create()
    results = {
        "status": "success",
        "traces": "pending",
        "logs": "pending",
        "metrics": "pending",
    }

    # --- Traces ---
    try:
        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(
            SimpleSpanProcessor(
                OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers)
            )
        )
        tracer = trace_provider.get_tracer("datarobot-otel-verification")
        with tracer.start_as_current_span("datarobot.otel.verification") as span:
            span.set_attribute("verification", True)
            span.set_attribute("source", "datarobot-external-agent-monitoring")
        trace_provider.shutdown()
        results["traces"] = "sent"
    except Exception as e:
        results["traces"] = f"error: {e}"
        results["status"] = "partial"

    # --- Logs ---
    try:
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            SimpleLogRecordProcessor(
                OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers)
            )
        )
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
        test_logger = logging.getLogger("datarobot-otel-verification")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)
        test_logger.info("DataRobot OTel verification — test log record")
        test_logger.removeHandler(handler)
        logger_provider.shutdown()
        results["logs"] = "sent"
    except Exception as e:
        results["logs"] = f"error: {e}"
        results["status"] = "partial"

    # --- Metrics ---
    try:
        preferred_temporality = {
            Counter: AggregationTemporality.DELTA,
            Histogram: AggregationTemporality.DELTA,
            ObservableCounter: AggregationTemporality.DELTA,
        }
        meter_provider = MeterProvider(
            metric_readers=[
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=f"{endpoint}/v1/metrics",
                        headers=headers,
                        preferred_temporality=preferred_temporality,
                    )
                )
            ],
            resource=resource,
        )
        meter = meter_provider.get_meter("datarobot-otel-verification")
        counter = meter.create_counter("datarobot.otel.verification", unit="1")
        counter.add(1, {"source": "verification"})
        meter_provider.shutdown()
        results["metrics"] = "sent"
    except Exception as e:
        results["metrics"] = f"error: {e}"
        results["status"] = "partial"

    return results


if __name__ == "__main__":
    result = verify_connection()
    print(json.dumps(result, indent=2))
    if result["status"] != "success":
        sys.exit(1)
