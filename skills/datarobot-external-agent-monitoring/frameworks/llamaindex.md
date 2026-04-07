# LlamaIndex — DataRobot OTel Integration

## Overview

LlamaIndex works with the standard `configure_otel()` pattern — it does NOT override the global TracerProvider. Use the generic `dr_otel_config.py` without modification.

Auto-instrumentation is available via `opentelemetry-instrumentation-llamaindex`, which creates spans for query engines, retrievers, LLM calls, and embedding operations.

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

# Auto-instrument LlamaIndex — must be called AFTER configure_otel()
from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor
LlamaIndexInstrumentor().instrument()

# Your LlamaIndex code below...
```

The auto-instrumentor captures:
- Query engine executions
- Retriever operations (vector search, keyword search)
- LLM calls (prompts, completions, token usage)
- Embedding generation
- Node postprocessing

## Extra Dependencies

```
opentelemetry-instrumentation-llamaindex
```

## Alternative: LlamaIndex Built-in Callback

LlamaIndex also has a built-in OpenTelemetry callback handler. If the auto-instrumentor package is unavailable or incompatible:

```python
from llama_index.core.callbacks import CallbackManager
from llama_index.core.callbacks.open_inference_callback import OpenInferenceCallbackHandler

callback_manager = CallbackManager([OpenInferenceCallbackHandler()])
# Pass callback_manager to your index/query engine
```

Prefer the auto-instrumentor when available — it's more comprehensive and doesn't require modifying query engine construction.

## Known Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| No spans from LlamaIndex | Instrumentor not called | Ensure `LlamaIndexInstrumentor().instrument()` is called AFTER `configure_otel()` |
| Import path changed | LlamaIndex v0.10+ restructured packages | Check if instrumentation package matches your LlamaIndex version |
| Missing embedding spans | Old instrumentor version | Update to latest `opentelemetry-instrumentation-llamaindex` |
