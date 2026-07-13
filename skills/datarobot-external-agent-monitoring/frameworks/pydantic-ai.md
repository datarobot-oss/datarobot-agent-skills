# PydanticAI — DataRobot OTel Integration

## Overview

PydanticAI does NOT override the global `TracerProvider`, so the generic
`dr_otel_config.py` works unchanged — but **OpenTelemetry instrumentation is opt-in**. Configuring a provider with
`configure_otel()` is necessary but **not sufficient**: without an explicit
`Agent.instrument_all()` call, PydanticAI emits **no spans**. There is no error —
telemetry simply never appears in DataRobot.

PydanticAI also has built-in integration with Pydantic Logfire, which exports
OTel-compatible telemetry. The preferred approach for DataRobot is direct OTel setup
(no Logfire dependency needed) plus the required `instrument_all()` opt-in.

## OTel Strategy

| Signal    | Strategy                                                            |
|-----------|--------------------------------------------------------------------|
| **Traces**  | Standard `configure_otel()` **+ required `Agent.instrument_all()`** (opt-in) |
| **Metrics** | Standard setup (optional custom metrics)                           |
| **Logs**    | Standard setup                                                     |

## Required Setup

### 1. Use the generic `dr_otel_config.py` as-is

No modifications to the config module. Call `configure_otel()` at startup, before any
PydanticAI import or agent creation.

### 2. Opt in to instrumentation and wire the entrypoint

Call `Agent.instrument_all()` after `configure_otel()`. This is the step that makes
PydanticAI emit spans; skipping it is the most common cause of "no telemetry."

```python
import os

from dr_otel_config import configure_otel

configure_otel()  # sets the global TracerProvider (additive) BEFORE PydanticAI opt-in

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# Opt in to PydanticAI's OTel instrumentation — without this, no spans are emitted.
Agent.instrument_all()

# Example: routing through the DataRobot LLM Gateway (any provider works).
provider = OpenAIProvider(
    base_url=f"{os.environ['DATAROBOT_ENDPOINT'].rstrip('/')}/genai/llmgw",
    api_key=os.environ["DATAROBOT_API_TOKEN"],
)
model = OpenAIChatModel("azure/gpt-5-mini-2025-08-07", provider=provider)

agent = Agent(model, system_prompt="You are a helpful assistant.")
```

`Agent.instrument_all()` uses the global `TracerProvider` that `configure_otel()` set,
so every agent in the process exports to DataRobot without editing each `Agent(...)`
constructor. PydanticAI creates spans for agent runs, LLM API calls, tool/function
calls, and retries/error handling.

## Version robustness

PydanticAI's instrumentation API has changed across versions. Prefer the global call;
fall back to per-agent only if you cannot call `instrument_all()` at startup.

- **Recommended — global, version-robust:**
  ```python
  Agent.instrument_all()
  ```

- **Per-agent alternative — PydanticAI v2.x:**
  ```python
  from pydantic_ai import Agent
  from pydantic_ai.capabilities import Instrumentation
  from pydantic_ai.models.instrumented import InstrumentationSettings

  agent = Agent(
      model,
      capabilities=[Instrumentation(settings=InstrumentationSettings())],
  )
  ```

- **Per-agent alternative — older PydanticAI v1.x:**
  ```python
  agent = Agent(model, instrument=True)
  ```

- **`InstrumentationSettings(version=…)`** controls the telemetry data format
  (`Literal[2, 3, 4, 5]`, default `5`, following OTel GenAI semantic conventions
  1.37.0). Versions 2–4 are deprecated and emit `PydanticAIDeprecationWarning`. Only
  pin a version if you must match a specific downstream schema (see Verify below).

- **Privacy — exclude prompt/completion content:**
  ```python
  from pydantic_ai import Agent
  from pydantic_ai.models.instrumented import InstrumentationSettings

  Agent.instrument_all(InstrumentationSettings(include_content=False))
  ```
  By default PydanticAI captures prompt and completion text in spans. Set
  `include_content=False` to suppress it (this also empties DataRobot's
  Prompt/Completion columns).

## Verify

After wiring, confirm telemetry lands in DataRobot: run the agent once, then check the
Use Case Tracing view (or the `dr xp` panel — see SKILL.md Step 5).

- **Spans present, Prompt/Completion columns populated** → done.
- **No spans at all** → `Agent.instrument_all()` was not called, or `configure_otel()`
  ran after agent creation. Fix ordering.
- **Spans present but Prompt/Completion columns empty** → attribute-name mismatch.
  PydanticAI's default `version=5` emits `gen_ai.input.messages` /
  `gen_ai.output.messages` (OTel GenAI semconv), while DataRobot's tracing table reads
  `gen_ai.prompt` / `gen_ai.completion`. To fix, add the `gen_ai.prompt` / `gen_ai.completion` span attributes yourself — note that **no** `InstrumentationSettings(version=…)` value produces them (every selectable format, 2–5, emits `gen_ai.input.messages` / `gen_ai.output.messages`), so pinning a version does not help. Also confirm `include_content` is not `False`, and check whether your DataRobot instance already normalizes the newer semconv attributes.

## Optional: Logfire instrumentation

If the user already uses Logfire or wants richer PydanticAI-specific spans:

```python
import logfire

logfire.configure(send_to_logfire=False)  # don't send to Logfire cloud; keep global provider
logfire.instrument_pydantic_ai()
```

This layers detailed Pydantic validation spans on top of the standard OTel traces. Use
either direct OTel (`instrument_all()`) or Logfire, not both, to avoid duplicate traces.

## Extra Dependencies

None beyond the generic OTel packages.

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
        request_counter.add(1, {"status": "success"})
        return result
    except Exception:
        request_counter.add(1, {"status": "error"})
        raise
    finally:
        request_duration.record((time.time() - start) * 1000)
```

## Known Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| No spans from PydanticAI | `Agent.instrument_all()` never called (instrumentation is opt-in) | Call `Agent.instrument_all()` after `configure_otel()`, before running agents |
| No spans from PydanticAI | `configure_otel()` called after agent creation | Ensure `configure_otel()` runs before any PydanticAI import or agent instantiation |
| Spans appear but Prompt/Completion columns empty | v5 semconv attributes (`gen_ai.input.messages`) differ from DataRobot's `gen_ai.prompt`/`gen_ai.completion`; or `include_content=False` | Add the `gen_ai.prompt`/`gen_ai.completion` span attributes yourself (no `version` value emits them); ensure `include_content` is not `False` (see Verify) |
| Logfire overrides TracerProvider | `logfire.configure()` called with default settings | Use `send_to_logfire=False` to keep the global provider |
| Duplicate traces | Both direct OTel and Logfire active | Choose one approach — prefer direct OTel |
