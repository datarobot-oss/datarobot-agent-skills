---
name: datarobot-external-agent-monitoring
description: Instrument any external AI agent with OpenTelemetry to send traces, logs, and metrics to DataRobot for monitoring, observability, and governance.
---

# DataRobot External Agent Monitoring Skill

This skill helps you instrument any AI agent — regardless of framework or deployment environment — to send OpenTelemetry telemetry (traces, logs, metrics) to DataRobot. It also creates a shell deployment in DataRobot as the telemetry routing target.

## Quick Start

**Most common use case**: Instrument an existing agent project for DataRobot monitoring

1. Point the agent at your project directory
2. The skill detects your framework and existing OTel setup
3. It generates instrumentation code and creates a DataRobot shell deployment
4. Your agent sends traces, logs, and metrics to DataRobot

**Example**: "Instrument my agent in ./my_agent for DataRobot monitoring"

## When to use this skill

Use this skill when you need to:
- Monitor an external AI agent in DataRobot
- Add OpenTelemetry tracing to an agent project
- Send agent traces, logs, and metrics to DataRobot
- Create a DataRobot deployment to receive external agent telemetry
- Instrument a Google ADK, LangChain, LangGraph, CrewAI, LlamaIndex, PydanticAI, or any Python agent

## Supported Frameworks

| Framework | Detection | OTel Strategy |
|-----------|-----------|---------------|
| Google ADK | `google-adk` in deps or `google.adk` in imports | Lazy trace injection via callback (ADK overwrites TracerProvider) |
| LangChain / LangGraph | `langchain` or `langgraph` in deps/imports | Auto-instrumentor + standard setup |
| CrewAI | `crewai` in deps/imports | Auto-instrumentor + standard setup |
| LlamaIndex | `llama-index` or `llama_index` in deps/imports | Auto-instrumentor + standard setup |
| PydanticAI | `pydantic-ai` or `pydantic_ai` in deps/imports | Standard setup (respects global TracerProvider) |
| Generic Python | None of the above detected | Manual span instrumentation |

## Workflow

Follow these steps in order. Present the plan to the user and wait for approval before executing.

### Step 1: Detect & Analyze

1. Read the project's dependency file (`requirements.txt`, `pyproject.toml`, `setup.py`, `poetry.lock`, or `uv.lock`)
2. Scan Python source files for framework imports
3. Check for existing OTel setup (look for `opentelemetry` imports, existing TracerProvider/LoggerProvider/MeterProvider configuration)
4. Identify the framework using the detection table above
5. Read the corresponding framework reference file from the `frameworks/` directory next to this SKILL.md:
   - Google ADK → `frameworks/google-adk.md`
   - LangChain/LangGraph → `frameworks/langchain-langgraph.md`
   - CrewAI → `frameworks/crewai.md`
   - LlamaIndex → `frameworks/llamaindex.md`
   - PydanticAI → `frameworks/pydantic-ai.md`
   - Generic Python → `frameworks/generic-python.md`

### Step 2: Check Prerequisites

1. Check if `DATAROBOT_API_TOKEN` env var is set. If not, ask the user to provide it.
2. Check if `DATAROBOT_ENDPOINT` env var is set. If not, ask the user (default: `https://app.datarobot.com/api/v2`).
3. Derive `DATAROBOT_OTEL_ENDPOINT` automatically: if `DATAROBOT_ENDPOINT` ends with `/api/v2`, strip it and append `/otel` (e.g., `https://app.datarobot.com/api/v2` → `https://app.datarobot.com/otel`).
4. Check if the `datarobot` Python SDK is available. If not, install it: `pip install datarobot`.
5. Check if OTel packages are already in the project's dependencies.

**Security note:** Never echo API tokens or `.env` file contents into chat transcripts or logs. Use environment variables or CI secrets for credential management. If credentials are accidentally exposed, rotate them immediately.

### Step 3: Present Plan

Tell the user what you detected and present the changes you will make:
- Framework detected (or generic Python)
- Existing OTel setup found (if any)
- New dependencies to add
- New files to create (`dr_otel_config.py`, and optionally `dr_agent_metrics.py` for frameworks with custom metrics)
- Existing files to modify (agent entrypoint, dependency file)
- Shell deployment to create in DataRobot

**Wait for user approval before executing.** If the user has already given explicit consent to implement or deploy, that counts as approval — no need to re-ask.

### Step 4: Execute

1. **Add dependencies** to the project's dependency file:
   - `opentelemetry-sdk`
   - `opentelemetry-api`
   - `opentelemetry-exporter-otlp-proto-http`
   - Framework-specific packages (see framework reference file)

2. **Generate `dr_otel_config.py`** using the generic pattern below, adapted per the framework reference file.

3. **Wire into agent entrypoint**: Add import and call to `configure_otel()` at startup. Follow the framework reference file for specific wiring instructions (auto-instrumentors, callbacks, etc.).

4. **Generate `dr_agent_metrics.py`** if the framework reference file specifies custom metrics callbacks.

5. **Create shell deployment**: Run the helper script:
   ```bash
   python <skill_scripts_dir>/create_shell_deployment.py \
     --name "<project_name> Monitoring" \
     --description "OTel telemetry sink for <framework> agent"
   ```

   The script automatically enables **prediction row storage** and **automatic association ID generation** on the deployment.

6. **Report results**: Show the deployment ID and a copy-paste env var block for the user's runtime:
   ```bash
   export DATAROBOT_API_TOKEN="<token>"
   export DATAROBOT_ENTITY_ID="deployment-<id>"
   export DATAROBOT_OTEL_ENDPOINT="<otel_endpoint>"
   ```

### Step 5: Verify & Provide Runtime Instructions

1. Optionally run the verification script:
   ```bash
   DATAROBOT_API_TOKEN=<token> \
   DATAROBOT_ENTITY_ID=deployment-<id> \
   DATAROBOT_OTEL_ENDPOINT=<endpoint>/otel \
   python <skill_scripts_dir>/verify_otel_connection.py
   ```

2. Provide the user with the env vars to set in their deployment environment:
   - `DATAROBOT_API_TOKEN` — DataRobot API key
   - `DATAROBOT_ENTITY_ID` — `deployment-<id>` (from shell deployment creation)
   - `DATAROBOT_OTEL_ENDPOINT` — `{DATAROBOT_ENDPOINT}/otel`

3. Explain what they'll see in DataRobot:
   - **Data Exploration > Traces**: Span hierarchy (agent orchestration, LLM calls, tool calls)
   - **Data Exploration > Logs**: Structured logs correlated with traces via traceId
   - **Data Exploration > Metrics**: Custom metrics (request count, latency, LLM calls, tool calls)

## Generic OTel Configuration Pattern

This is the core `configure_otel()` function to generate for every project. Framework-specific files layer additional setup on top.

**Critical rules:**
1. Always pass `endpoint=` and `headers=` directly to exporters — NEVER use `OTEL_EXPORTER_OTLP_*` env vars (some frameworks detect these and create conflicting providers)
2. Be additive — add DataRobot as an additional span processor to any existing TracerProvider, don't replace it
3. Use `SimpleSpanProcessor` (not Batch) to avoid flush-before-shutdown issues
4. Use DELTA temporality for metrics (required by DataRobot)

**Generated `dr_otel_config.py` template:**

```python
"""DataRobot OpenTelemetry configuration.

Configures traces, logs, and metrics export to DataRobot's OTel endpoint.
Call configure_otel() at application startup, before any agent code runs.

Required env vars at runtime:
    DATAROBOT_API_TOKEN      - DataRobot API key
    DATAROBOT_ENTITY_ID      - deployment-<deployment_id>
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
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider, ObservableCounter
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
        logging.warning("DATAROBOT_API_TOKEN not set — OTel export to DataRobot will fail")
    if not entity_id:
        logging.warning("DATAROBOT_ENTITY_ID not set — OTel export to DataRobot will fail")
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
    resource = Resource.create()

    # --- Traces ---
    dr_span_processor = SimpleSpanProcessor(
        OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers)
    )
    existing_provider = trace.get_tracer_provider()
    if hasattr(existing_provider, "add_span_processor"):
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

**OTel provider initialization order warning:**

Some frameworks override the global TracerProvider at startup (notably Google ADK). When this happens, the standard trace setup above will lose the DataRobot exporter. The framework reference files document which frameworks have this issue and provide alternative patterns (e.g., lazy injection via callbacks). Always check the framework reference file.

Existing OTel setups (e.g., exporters to Jaeger, Datadog, Google Cloud Trace) are preserved when possible — DataRobot is added alongside, not replacing. However, note that OTel has a single global provider per signal. Whoever calls `set_tracer_provider()` last wins. The additive pattern above avoids calling `set_tracer_provider()` when a provider already exists, instead adding a processor to the existing one.

## DataRobot Tracing Table — Span Attribute Mapping

DataRobot's tracing UI (Data Exploration > Traces) maps specific span attributes to table columns. Using the correct attribute names is critical for data to appear in the dashboard.

### Column Mapping

| Tracing Table Column | Span Attribute | Aggregation Rule |
|---------------------|----------------|------------------|
| **Prompt** | `gen_ai.prompt` | First span with this attribute wins |
| **Completion** | `gen_ai.completion` | Last span with this attribute wins |
| **Tools** | `tool_name` | Lists all unique values across all spans in the trace |
| **Cost** | `datarobot.moderation.cost` | Summed across all spans in the trace |

**Important:** DataRobot looks for `tool_name` (underscore), NOT `tool.name` (dot). Some frameworks (e.g., LangGraph) do not set `tool_name` by default — you must add it manually as a span attribute inside each tool call.

### All Recognized Span Attributes

| Attribute | Description | Example |
|-----------|-------------|---------|
| `gen_ai.prompt` | User input / prompt text | `"Analyze policy XYZ"` |
| `gen_ai.completion` | Model output / response | `"Policy matched..."` |
| `gen_ai.request.model` | Model used for the call | `"gpt-4o"` |
| `gen_ai.usage.prompt_tokens` | Input token count | `150` |
| `gen_ai.usage.completion_tokens` | Output token count | `320` |
| `tool_name` | Name of tool/function called (required for Tools column) | `"search_database"` |
| `tool.parameters` | Tool call parameters (JSON string) | `'{"query": "..."}'` |
| `datarobot.moderation.cost` | Cost of this span (summed for trace total) | `0.0023` |

## Helper Scripts

### create_shell_deployment.py

Creates a shell deployment in DataRobot as a telemetry routing target.

```bash
python <scripts_dir>/create_shell_deployment.py \
  --name "My Agent Monitoring" \
  --description "OTel telemetry sink for my agent"
```

Requires env vars: `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT`

Returns JSON:
```json
{
  "deployment_id": "abc123",
  "entity_id": "deployment-abc123",
  "otel_endpoint": "https://app.datarobot.com/otel"
}
```

### verify_otel_connection.py

Sends test telemetry to verify the OTel pipeline is working.

```bash
python <scripts_dir>/verify_otel_connection.py
```

Requires env vars: `DATAROBOT_API_TOKEN`, `DATAROBOT_ENTITY_ID`, `DATAROBOT_OTEL_ENDPOINT`

Returns JSON:
```json
{
  "status": "success",
  "traces": "sent",
  "logs": "sent",
  "metrics": "sent"
}
```

## Dependencies

Required for instrumentation (added to user's project):
```
opentelemetry-sdk
opentelemetry-api
opentelemetry-exporter-otlp-proto-http
```

Required for shell deployment creation (available in the skill's script environment):
```
datarobot
```

## Best practices

1. **Call `configure_otel()` before any agent/framework initialization** — some frameworks capture the provider at import time
2. **Never set `OTEL_EXPORTER_OTLP_*` env vars** — pass endpoint and headers directly to exporters to avoid conflicts
3. **Use `SimpleSpanProcessor`** over `BatchSpanProcessor` — avoids flush issues on short-lived processes
4. **DELTA temporality for metrics** — DataRobot requires delta aggregation for counters and histograms
5. **Check framework reference files** for initialization order issues before generating code

## Error handling

Common errors and solutions:

| Error | Cause | Solution |
|-------|-------|----------|
| Traces not appearing in DataRobot | Framework overwrites TracerProvider | Use lazy injection pattern (see framework reference) |
| 401 Unauthorized from OTel endpoint | Invalid API token | Verify `DATAROBOT_API_TOKEN` is correct |
| 404 from OTel endpoint | Wrong endpoint URL | Ensure `DATAROBOT_OTEL_ENDPOINT` ends with `/otel` |
| Metrics not appearing | `OTEL_EXPORTER_OTLP_*` env vars set | Remove env vars, use direct exporter config |
| `DATAROBOT_ENTITY_ID` format error | Missing `deployment-` prefix | Must be `deployment-<id>`, not just `<id>` |

## Resources

- [DataRobot Model Monitoring Documentation](https://docs.datarobot.com/en/docs/mlops/monitor/index.html)
- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/)
- [OpenTelemetry OTLP Exporter](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html)
