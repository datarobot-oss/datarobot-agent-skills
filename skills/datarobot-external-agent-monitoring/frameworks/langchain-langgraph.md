# LangChain / LangGraph — DataRobot OTel Integration

## Overview

LangChain and LangGraph work with the standard `configure_otel()` pattern — they do NOT override the global TracerProvider. Use the generic `dr_otel_config.py` without modification.

Auto-instrumentation is available via `opentelemetry-instrumentation-langchain`, which automatically creates spans for chains, LLM calls, tool invocations, and retriever operations.

## OTel Strategy

| Signal    | Strategy                                    |
|-----------|---------------------------------------------|
| **Traces**  | Standard setup + auto-instrumentor         |
| **Metrics** | Standard setup (optional custom callbacks) |
| **Logs**    | Standard setup                             |

## Setup

### 1. Use the generic `dr_otel_config.py` as-is

No modifications needed. Call `configure_otel()` at startup.

### 2. Add auto-instrumentor after `configure_otel()`

In the agent's entrypoint:

```python
from dr_otel_config import configure_otel

configure_otel()

# Auto-instrument LangChain — must be called AFTER configure_otel()
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
LangchainInstrumentor().instrument()

# Your agent code below...
```

The auto-instrumentor captures:
- Chain executions (with input/output)
- LLM calls (model, prompt, completion, token usage)
- Tool/function calls
- Retriever operations (for RAG)
- Agent reasoning steps (for LangGraph)

**Important: `tool_name` attribute for DataRobot.** LangGraph does NOT set the `tool_name` span attribute by default. DataRobot's tracing table requires `tool_name` (underscore) to populate the Tools column. Add it manually inside your tools:

```python
from opentelemetry import trace

@tool
def search_database(query: str) -> str:
    """Search the database."""
    span = trace.get_current_span()
    span.set_attribute("tool_name", "search_database")
    # ... tool logic ...
```

Without this, tool spans will appear in the trace hierarchy but the Tools column in DataRobot will be empty.

### 3. Optional: Add OpenAI/Anthropic SDK instrumentors

If the agent uses OpenAI or Anthropic SDKs directly (in addition to LangChain), add their instrumentors too:

```python
# Optional — for direct SDK calls outside LangChain
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
OpenAIInstrumentor().instrument()
```

## Extra Dependencies

```
opentelemetry-instrumentation-langchain
```

Optional:
```
opentelemetry-instrumentation-openai      # If using OpenAI SDK directly
opentelemetry-instrumentation-anthropic    # If using Anthropic SDK directly
```

## Custom Metrics (Optional)

LangChain/LangGraph agents don't require a custom metrics callback module — the auto-instrumentor handles trace spans. For custom metrics (request counts, latency histograms), you can optionally add a LangChain callback handler:

```python
from opentelemetry import metrics

meter = metrics.get_meter("my-langchain-agent")
request_counter = meter.create_counter("agent.requests", unit="1")
request_duration = meter.create_histogram("agent.request.duration_ms", unit="ms")

# Use LangChain's callback system to record metrics
from langchain_core.callbacks import BaseCallbackHandler

class DataRobotMetricsHandler(BaseCallbackHandler):
    def on_chain_start(self, serialized, inputs, **kwargs):
        import time
        kwargs.setdefault("metadata", {})["_dr_start"] = time.time()

    def on_chain_end(self, outputs, **kwargs):
        import time
        start = kwargs.get("metadata", {}).get("_dr_start", time.time())
        elapsed_ms = (time.time() - start) * 1000
        request_counter.add(1, {"status": "success"})
        request_duration.record(elapsed_ms)

    def on_chain_error(self, error, **kwargs):
        request_counter.add(1, {"status": "error"})
```

This is optional — the auto-instrumentor already provides comprehensive trace spans.

## Known Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| No spans from LangChain | Instrumentor not called | Ensure `LangchainInstrumentor().instrument()` is called AFTER `configure_otel()` |
| Duplicate spans | Multiple instrumentors active | Only instrument once; check for existing instrumentation |
| Missing retriever spans | Old instrumentor version | Update `opentelemetry-instrumentation-langchain` to latest |
