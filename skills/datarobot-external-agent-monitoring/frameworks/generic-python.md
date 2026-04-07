# Generic Python — DataRobot OTel Integration

## Overview

For agents built without a specific framework (plain Python, custom frameworks, or frameworks not listed in the supported set), use the standard `configure_otel()` pattern with manual span instrumentation.

The coding agent should analyze the user's code and add spans around key operations: agent request handling, LLM calls, tool invocations, and data retrieval.

## OTel Strategy

| Signal    | Strategy                                |
|-----------|-----------------------------------------|
| **Traces**  | Standard setup + manual span instrumentation |
| **Metrics** | Standard setup + manual metric recording |
| **Logs**    | Standard setup                         |

## Setup

### 1. Use the generic `dr_otel_config.py` as-is

No modifications needed. Call `configure_otel()` at startup.

### 2. Add manual span instrumentation

After calling `configure_otel()`, create a tracer and wrap key operations:

```python
from dr_otel_config import configure_otel

configure_otel()

from opentelemetry import trace

tracer = trace.get_tracer("my-agent")


def handle_request(user_message: str) -> str:
    with tracer.start_as_current_span("agent-request") as span:
        span.set_attribute("gen_ai.prompt", user_message)

        # LLM call
        with tracer.start_as_current_span("llm-call") as llm_span:
            llm_span.set_attribute("gen_ai.request.model", "gpt-4o")
            response = call_llm(user_message)
            llm_span.set_attribute("gen_ai.completion", response)
            llm_span.set_attribute("gen_ai.usage.prompt_tokens", token_count)
            llm_span.set_attribute("gen_ai.usage.completion_tokens", completion_tokens)

        # Tool call
        with tracer.start_as_current_span("tool-call") as tool_span:
            tool_span.set_attribute("tool_name", "search_database")
            tool_span.set_attribute("tool.parameters", '{"query": "..."}')
            result = search_database(query)

        span.set_attribute("gen_ai.completion", final_response)
        return final_response
```

### 3. Add custom metrics

```python
from opentelemetry import metrics
import time

meter = metrics.get_meter("my-agent")

request_counter = meter.create_counter(
    "agent.requests", unit="1",
    description="Total requests processed",
)
request_duration = meter.create_histogram(
    "agent.request.duration_ms", unit="ms",
    description="End-to-end request duration",
)
llm_call_counter = meter.create_counter(
    "agent.llm.calls", unit="1",
    description="Number of LLM API calls",
)
llm_duration = meter.create_histogram(
    "agent.llm.duration_ms", unit="ms",
    description="Individual LLM call duration",
)
tool_call_counter = meter.create_counter(
    "agent.tool.calls", unit="1",
    description="Number of tool invocations",
)


def handle_request(user_message: str) -> str:
    start = time.time()
    try:
        # ... agent logic with spans as above ...
        elapsed_ms = (time.time() - start) * 1000
        request_counter.add(1, {"status": "success"})
        request_duration.record(elapsed_ms)
        return response
    except Exception:
        elapsed_ms = (time.time() - start) * 1000
        request_counter.add(1, {"status": "error"})
        request_duration.record(elapsed_ms)
        raise
```

## Span Attributes for DataRobot Tracing

Use these attributes for data to appear in DataRobot's tracing table:

| Attribute | Description | DataRobot Column | Rule |
|-----------|-------------|------------------|------|
| `gen_ai.prompt` | User input / prompt text | Prompt | First span wins |
| `gen_ai.completion` | Model output / response | Completion | Last span wins |
| `tool_name` | Tool/function name | Tools | All unique values listed |
| `datarobot.moderation.cost` | Cost of this operation | Cost | Summed across trace |
| `gen_ai.request.model` | Model used | — | Informational |
| `gen_ai.usage.prompt_tokens` | Input token count | — | Informational |
| `gen_ai.usage.completion_tokens` | Output token count | — | Informational |
| `tool.parameters` | Tool call parameters (JSON) | — | Informational |

**Important:** Use `tool_name` (underscore), not `tool.name` (dot). DataRobot's tracing UI specifically looks for `tool_name`.

## Auto-Instrumenting Common SDKs

Even without a framework, you can auto-instrument the underlying LLM SDKs:

```python
# OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
OpenAIInstrumentor().instrument()

# Anthropic
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
AnthropicInstrumentor().instrument()

# HTTP clients (catches all outbound API calls)
from opentelemetry.instrumentation.requests import RequestsInstrumentor
RequestsInstrumentor().instrument()

from opentelemetry.instrumentation.httpx import HTTPXInstrumentor
HTTPXInstrumentor().instrument()
```

## Extra Dependencies

None beyond the generic OTel packages.

Optional (for SDK auto-instrumentation):
```
opentelemetry-instrumentation-openai       # If using OpenAI SDK
opentelemetry-instrumentation-anthropic     # If using Anthropic SDK
opentelemetry-instrumentation-requests      # If using requests library
opentelemetry-instrumentation-httpx         # If using httpx library
```

## Guidance for the Coding Agent

When instrumenting a generic Python agent:

1. **Identify the request handler** — the function that receives user input and returns output. Wrap it in a root span (`agent-request`).
2. **Identify LLM calls** — any call to an LLM API (OpenAI, Anthropic, Vertex AI, etc.). Wrap each in a child span (`llm-call`) with `gen_ai.*` attributes.
3. **Identify tool calls** — any external operation (database, API, search, etc.). Wrap each in a child span (`tool-call`) with `tool.*` attributes.
4. **Add metrics** — at minimum, add request count and duration. Add LLM call count/duration and tool call count if identifiable.
5. **Don't over-instrument** — focus on the key operations. Not every function needs a span.
