# CrewAI — DataRobot OTel Integration

## Overview

CrewAI works with the standard `configure_otel()` pattern — it does NOT override the global TracerProvider. Use the generic `dr_otel_config.py` without modification.

Auto-instrumentation is available via `opentelemetry-instrumentation-crewai`, which creates spans for crew executions, agent tasks, tool calls, and LLM interactions.

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

# Auto-instrument CrewAI — must be called AFTER configure_otel()
from opentelemetry.instrumentation.crewai import CrewAIInstrumentor
CrewAIInstrumentor().instrument()

# Your crew code below...
```

The auto-instrumentor captures:
- Crew kickoff and execution
- Individual agent task execution
- Tool calls within tasks
- LLM interactions per agent

## Extra Dependencies

```
opentelemetry-instrumentation-crewai
```

## Custom Metrics (Optional)

For custom metrics beyond what the auto-instrumentor provides, use CrewAI's callback system:

```python
from opentelemetry import metrics

meter = metrics.get_meter("my-crewai-agent")
task_counter = meter.create_counter("agent.tasks.completed", unit="1")
crew_duration = meter.create_histogram("agent.crew.duration_ms", unit="ms")
```

Wire these into CrewAI's task callbacks or measure around `crew.kickoff()`.

## Known Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| No spans from CrewAI | Instrumentor not called | Ensure `CrewAIInstrumentor().instrument()` is called AFTER `configure_otel()` |
| Import error on instrumentor | Wrong package version | Ensure `opentelemetry-instrumentation-crewai` is compatible with your CrewAI version |
