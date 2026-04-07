# PydanticAI — DataRobot OTel Integration

## Overview

PydanticAI works with the standard `configure_otel()` pattern — it respects the global TracerProvider and does NOT override it. Use the generic `dr_otel_config.py` without modification.

PydanticAI has built-in integration with Pydantic Logfire, which exports OTel-compatible telemetry. The preferred approach for DataRobot integration is to use direct OTel setup (no logfire dependency needed).

## OTel Strategy

| Signal    | Strategy                                          |
|-----------|---------------------------------------------------|
| **Traces**  | Standard setup — PydanticAI respects global TracerProvider |
| **Metrics** | Standard setup (optional custom metrics)          |
| **Logs**    | Standard setup                                    |

## Preferred Setup: Direct OTel

### 1. Use the generic `dr_otel_config.py` as-is

No modifications needed. Call `configure_otel()` at startup.

### 2. Wire into agent entrypoint

```python
from dr_otel_config import configure_otel

configure_otel()

# PydanticAI automatically uses the global TracerProvider
from pydantic_ai import Agent

agent = Agent(
    "openai:gpt-4o",
    system_prompt="You are a helpful assistant.",
)
```

PydanticAI creates spans for:
- Agent runs (with input/output)
- LLM API calls (model, messages, response)
- Tool/function calls
- Retries and error handling

### 3. Optional: Enable Logfire instrumentation

If the user already uses Logfire or wants richer PydanticAI-specific spans:

```python
import logfire

logfire.configure(
    send_to_logfire=False,  # Don't send to Logfire cloud
    # Logfire respects the global TracerProvider set by configure_otel()
)
logfire.instrument_pydantic_ai()
```

This adds more detailed Pydantic validation spans on top of the standard OTel traces.

## Extra Dependencies

None beyond the generic OTel packages for the preferred approach.

Optional (if using Logfire):
```
logfire[pydantic-ai]
```

## Custom Metrics (Optional)

For custom metrics, wrap the agent run:

```python
import time
from opentelemetry import metrics

meter = metrics.get_meter("my-pydantic-agent")
request_counter = meter.create_counter("agent.requests", unit="1")
request_duration = meter.create_histogram("agent.request.duration_ms", unit="ms")

async def run_with_metrics(agent, prompt):
    start = time.time()
    try:
        result = await agent.run(prompt)
        elapsed_ms = (time.time() - start) * 1000
        request_counter.add(1, {"status": "success"})
        request_duration.record(elapsed_ms)
        return result
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        request_counter.add(1, {"status": "error"})
        request_duration.record(elapsed_ms)
        raise
```

## Known Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| No spans from PydanticAI | `configure_otel()` called after agent creation | Ensure `configure_otel()` is called before any PydanticAI imports or agent instantiation |
| Logfire overrides TracerProvider | `logfire.configure()` called with default settings | Use `send_to_logfire=False` to prevent Logfire from replacing the provider |
| Duplicate traces | Both direct OTel and Logfire active | Choose one approach — prefer direct OTel unless Logfire is already in use |
