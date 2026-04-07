# Google ADK — DataRobot OTel Integration

## Critical: ADK Overwrites the Global TracerProvider

Google ADK's web server calls `_setup_telemetry()` at startup, which **replaces any TracerProvider set earlier**. This means the standard `configure_otel()` trace setup will be overwritten. Logs and metrics are NOT affected.

| Signal    | ADK Overrides? | Strategy                                                        |
|-----------|----------------|-----------------------------------------------------------------|
| **Traces**  | YES            | Lazy injection — add span processor to ADK's provider on first request |
| **Metrics** | No*            | Standard setup at import time with direct exporter config       |
| **Logs**    | No             | Standard setup at import time                                   |

*ADK will override MeterProvider if `OTEL_EXPORTER_OTLP_*` env vars are set. Never set these.

## Modified `dr_otel_config.py` for ADK

For ADK, the generated `dr_otel_config.py` must be modified from the generic pattern:

1. **Do NOT configure traces in `configure_otel()`** — traces will be lost when ADK replaces the TracerProvider
2. **Build `dr_span_processor` at module level** — this is injected lazily later
3. **Export `dr_span_processor`** so the metrics callback module can access it
4. **Call `configure_otel()` at module level** (import time), not deferred

```python
# In dr_otel_config.py — ADK variant
# ... (same imports as generic, plus:)

def configure_otel():
    """Configure logs and metrics only. Traces use lazy injection."""
    headers = _build_dr_headers()
    endpoint = _get_endpoint()
    if not endpoint:
        return
    resource = Resource.create()

    # Logs — ADK does NOT override LoggerProvider
    # (same as generic pattern)

    # Logs — attach a custom Formatter so OTLP log bodies are never empty
    # (ADK and third-party code can emit records with empty getMessage())
    log_exporter = OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers)
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)

    # Metrics — direct exporter config (no env vars!)
    # Use a shorter export_interval_millis for serverless/short-lived workers.
    # Default 60s may miss metrics on Agent Engine playground or single-turn requests.
    metric_exporter = OTLPMetricExporter(
        endpoint=f"{endpoint}/v1/metrics",
        headers=headers,
        preferred_temporality=preferred_temporality,
    )
    meter_provider = MeterProvider(
        metric_readers=[PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=5000,
        )],
        resource=resource,
    )
    metrics.set_meter_provider(meter_provider)

    # NOTE: Traces are NOT configured here. See dr_span_processor below.


# Build trace processor at import time — injected lazily on first request.
# May be None if endpoint is not configured (e.g. local dev without DataRobot).
_ep = _get_endpoint()
if _ep:
    dr_span_processor: SimpleSpanProcessor | None = SimpleSpanProcessor(
        OTLPSpanExporter(
            endpoint=f"{_ep}/v1/traces",
            headers=_build_dr_headers(),
        )
    )
else:
    dr_span_processor = None

configure_otel()
```

## Custom Metrics Callback Module

Generate `dr_agent_metrics.py` with callbacks for ADK agent lifecycle events.

```python
"""DataRobot metrics instrumentation for ADK agent.

Callbacks for LlmAgent lifecycle events that record OTel metrics
and handle lazy trace injection into ADK's TracerProvider.
"""

import logging
import threading
import time

from opentelemetry import metrics, trace

_meter = metrics.get_meter("agent-name")  # Replace with actual agent name

request_counter = _meter.create_counter(
    "agent.requests", unit="1",
    description="Total requests processed by the agent",
)
request_duration = _meter.create_histogram(
    "agent.request.duration_ms", unit="ms",
    description="End-to-end agent request duration",
)
llm_call_counter = _meter.create_counter(
    "agent.llm.calls", unit="1",
    description="Number of LLM API calls made",
)
llm_duration = _meter.create_histogram(
    "agent.llm.duration_ms", unit="ms",
    description="Individual LLM call duration",
)
tool_call_counter = _meter.create_counter(
    "agent.tool.calls", unit="1",
    description="Number of tool invocations",
)

_t = threading.local()
_trace_injected = False
_inject_warned = False


def _resolve_tracer_provider_for_processor():
    """Resolve SDK TracerProvider; skip API ``ProxyTracerProvider``.

    ``trace.get_tracer_provider()`` often returns ``ProxyTracerProvider``, which does
    **not** implement ``add_span_processor``. The real SDK provider is on
    ``opentelemetry.trace._TRACER_PROVIDER`` once something (e.g. ADK) has called
    ``set_tracer_provider``.
    """
    import opentelemetry.trace as trace_module

    candidates = []
    internal = getattr(trace_module, "_TRACER_PROVIDER", None)
    if internal is not None:
        candidates.append(internal)
    candidates.append(trace.get_tracer_provider())

    for entry in candidates:
        cur = entry
        for _ in range(5):
            if cur is None:
                break
            if type(cur).__name__ != "ProxyTracerProvider" and hasattr(cur, "add_span_processor"):
                return cur
            cur = getattr(cur, "_real_tracer_provider", None)
    return None


def _ensure_trace_export():
    """Inject DataRobot span processor on first successful resolution of SDK provider."""
    global _trace_injected, _inject_warned
    if _trace_injected:
        return
    try:
        import dr_otel_config

        proc = dr_otel_config.dr_span_processor
        if proc is None:
            logging.debug("DataRobot span processor not configured (missing OTEL endpoint)")
            return

        target = _resolve_tracer_provider_for_processor()
        if target is not None:
            target.add_span_processor(proc)
            _trace_injected = True
            logging.info(
                "Injected DataRobot span processor into TracerProvider (%s)",
                type(target).__name__,
            )
        elif not _inject_warned:
            _inject_warned = True
            logging.warning(
                "DataRobot trace export: no SDK TracerProvider yet (will retry on later callbacks)"
            )
    except Exception as e:
        logging.error("Failed to inject DataRobot span processor: %s", e)


async def before_agent(callback_context):
    """Called before agent processes a request. Injects trace export on first call."""
    _ensure_trace_export()
    _t.agent_start = time.time()
    return None


async def after_agent(callback_context):
    """Called after agent completes. NOTE: only 1 argument, not 2."""
    elapsed_ms = (time.time() - getattr(_t, "agent_start", time.time())) * 1000
    request_counter.add(1, {"status": "success"})
    request_duration.record(elapsed_ms)
    # Flush DELTA metrics so they export before the worker ends.
    # Critical for serverless / short-lived workers where the periodic reader
    # may not tick before shutdown.
    try:
        mp = metrics.get_meter_provider()
        if hasattr(mp, "force_flush"):
            mp.force_flush(timeout_millis=5000)
    except Exception:
        pass
    return None


async def before_model(callback_context, llm_request):
    """Called before each LLM API call."""
    _ensure_trace_export()
    _t.llm_start = time.time()
    return None


async def after_model(callback_context, llm_response):
    """Called after each LLM API call."""
    elapsed_ms = (time.time() - getattr(_t, "llm_start", time.time())) * 1000
    model = getattr(llm_response, "model", "unknown") or "unknown"
    llm_call_counter.add(1, {"model": model})
    llm_duration.record(elapsed_ms, {"model": model})
    return None


async def after_tool(tool, args, tool_context, tool_response):
    """Called after each tool invocation."""
    name = getattr(tool, "name", "unknown") or "unknown"
    tool_call_counter.add(1, {"tool": str(name)})
    # Set tool_name on the current span so DataRobot's tracing table shows it
    # in the Tools column. DataRobot looks for "tool_name" (underscore), not "tool.name".
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute("tool_name", str(name))
    return None
```

## Wiring Callbacks to ADK Agents

For multi-agent setups, use different callback sets for root vs sub-agents:
- **Root agent**: All callbacks (trace injection, request metrics, LLM/tool metrics)
- **Sub-agents**: Only LLM and tool metrics (avoids double-counting requests and thread-local corruption)

```python
import dr_otel_config  # noqa: F401 — configures logs/metrics at import
import dr_agent_metrics

# Root agent: trace injection + end-to-end request metrics + LLM/tool metrics
_ADK_DR_ROOT = {
    "before_agent_callback": dr_agent_metrics.before_agent,
    "after_agent_callback": dr_agent_metrics.after_agent,
    "before_model_callback": dr_agent_metrics.before_model,
    "after_model_callback": dr_agent_metrics.after_model,
    "after_tool_callback": dr_agent_metrics.after_tool,
}

# Sub-agents: LLM and tool metrics only (no request counting or trace injection)
_ADK_DR_SUB = {
    "before_model_callback": dr_agent_metrics.before_model,
    "after_model_callback": dr_agent_metrics.after_model,
    "after_tool_callback": dr_agent_metrics.after_tool,
}

search_agent = LlmAgent(
    name="search_agent",
    model="gemini-2.5-flash",
    # ...
    **_ADK_DR_SUB,
)

root_agent = LlmAgent(
    name="my_agent",
    model="gemini-2.5-flash",
    tools=[AgentTool(agent=search_agent)],
    # ...
    **_ADK_DR_ROOT,
)
```

**Important**: Import `dr_otel_config` before `dr_agent_metrics` to ensure logs and metrics providers are set before metrics instruments are created.

**Warning about thread-local state**: `before_agent`/`after_agent` use `threading.local()` for timing. Wiring these on sub-agents can corrupt timing if a sub-agent runs in the same thread as the root. Keep request-level callbacks on the root only.

## Deployment Prerequisites

### GCP / Vertex AI Agent Engine

Before deploying, verify:
- [ ] Google Application Default Credentials configured (`gcloud auth application-default login` or `GOOGLE_APPLICATION_CREDENTIALS`)
- [ ] Correct `GOOGLE_CLOUD_PROJECT` set
- [ ] Required APIs enabled (Vertex AI, Agent Engine)
- [ ] GCS staging bucket accessible (if using Agent Engine)
- [ ] `DATAROBOT_API_TOKEN`, `DATAROBOT_ENTITY_ID`, `DATAROBOT_OTEL_ENDPOINT` set in the **deployed** agent's environment (not just local). These must be injected into Agent Engine via deployment env vars, Secret Manager, or the deploy script.
- [ ] Optional: `OTEL_SERVICE_NAME` for consistent `service.name` across all OTel signals

**Common mistake:** Local `verify_otel_connection.py` passes because `DATAROBOT_*` env vars exist on your machine, but deployed Agent Engine has no telemetry because those vars weren't passed to the container.

### Cloud Run

- [ ] Same `DATAROBOT_*` env vars set via `gcloud run services update --set-env-vars`
- [ ] No `OTEL_EXPORTER_OTLP_*` env vars (conflicts with DataRobot-specific export)

### Docker / Kubernetes

- [ ] Inject `DATAROBOT_*` env vars at runtime (docker-compose, k8s ConfigMap/Secret)
- [ ] No `OTEL_EXPORTER_OTLP_*` env vars for DataRobot-specific exporters

## Extra Dependencies

Add to the project's dependency file **if deploying to GCP** (Cloud Run, Agent Engine, GKE):
```
opentelemetry-resourcedetector-gcp
```

This package adds GCP resource attributes (project ID, region, service name) to spans. **Omit it for non-GCP deployments** (Docker, k8s on AWS/Azure, local dev) — it adds unnecessary weight and may log warnings about missing GCP metadata.

Note: The package name is `opentelemetry-resourcedetector-gcp` (no hyphen between "resource" and "detector"). Getting this wrong causes build failures.

## Known Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| Traces not appearing | ADK replaced TracerProvider | Verify `_ensure_trace_export()` fires (check logs for "Injected DataRobot span processor") |
| `TracerProvider does not support add_span_processor` | `get_tracer_provider()` returned `ProxyTracerProvider` | Use `_resolve_tracer_provider_for_processor()` (reads `opentelemetry.trace._TRACER_PROVIDER`); call `_ensure_trace_export()` from `before_model` too so injection retries after ADK inits the SDK |
| `after_agent() missing 1 required positional argument` | Wrong callback signature | `after_agent(callback_context)` takes 1 arg, not 2 |
| Callbacks not called | Not `async` | All ADK callbacks must be `async def` (ADK v1.18+) |
| Metrics missing | `OTEL_EXPORTER_OTLP_*` env vars set | Remove all `OTEL_EXPORTER_OTLP_*` env vars |
| Build fails on `opentelemetry-resource-detector-gcp` | Wrong package name | Correct: `opentelemetry-resourcedetector-gcp` |
| ADK creates duplicate spans | ADK detects OTEL env vars | Never set `OTEL_EXPORTER_OTLP_ENDPOINT` or similar env vars |
| Metrics never reach DataRobot | `dr_agent_metrics` imported before `dr_otel_config` | `get_meter()` binds to the no-op provider. Import `dr_otel_config` first (it calls `configure_otel()` + `set_meter_provider` at import time) |
| Metrics missing on short requests | `PeriodicExportingMetricReader` default 60s interval | Set `export_interval_millis=5000` and call `force_flush` in `after_agent` |
| Empty OTLP log bodies | ADK/library log records with empty `getMessage()` | Attach `logging.Formatter("%(levelname)s %(name)s: %(message)s")` on the `LoggingHandler` |
| Local verify passes but Engine has no telemetry | `DATAROBOT_*` env vars not in deployed container | Copy env vars to Agent Engine deploy script / Secret Manager |
