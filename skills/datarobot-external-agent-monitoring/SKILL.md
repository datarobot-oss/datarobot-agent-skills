---
name: datarobot-external-agent-monitoring
description: Instrument any external or existing AI agent with OpenTelemetry to send traces, logs, and metrics to DataRobot for monitoring, observability, and governance. Use when the user says "add tracing/observability/monitoring to my agent", wants to instrument an existing agent project in their IDE, or wants to send agent traces, logs, or metrics to DataRobot.
---

# DataRobot External Agent Monitoring Skill

This skill helps you instrument any AI agent — regardless of framework or deployment environment — to send OpenTelemetry telemetry (traces, logs, metrics) to DataRobot. It also creates a shell deployment in DataRobot as the telemetry routing target.

## Quick Start

**Most common use case**: Instrument an existing agent project, regardless of whether it was built on DataRobot or elsewhere, with DataRobot monitoring

1. The user invokes the skill from inside their project — typically: "Add tracing to my agent"
2. The skill resolves the target project (current IDE workspace / working directory if no path is given), then detects the framework and any existing OTel setup
3. It resolves a **Use Case** as the telemetry target (asks for the user's Use Case ID, or offers to create one), generates instrumentation code, and wires it in
4. The agent sends traces, logs, and metrics to DataRobot, where they appear under the Use Case's Tracing tab

**Examples**:
- "Add tracing to my agent" (resolves to the current workspace)
- "Instrument my agent in ./my_agent for DataRobot monitoring"

## When to use this skill

Use this skill when an existing DataRobot user has built an agent elsewhere and wants to bring it in for monitoring. Specifically:
- Bring an externally-built (brownfield) agent into DataRobot for monitoring under a Use Case
- Add OpenTelemetry tracing to an agent project
- Send agent traces, logs, and metrics to DataRobot
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

1. Ensure `DATAROBOT_API_TOKEN` is available **without having the user paste it into chat** (a pasted token would be logged in the transcript). Check the environment and the project `.env`. If the token is missing, create or update a project `.env` file with the DataRobot variables and have the user paste their Personal API key into **that file** directly (in their editor); read it from there. Ensure `.env` is gitignored. This skill targets existing DataRobot users: create a Personal API key at `<your DataRobot URL>/account/developer-tools` (Personal API keys tab; see the `datarobot-setup` skill). (No DataRobot account at all? https://www.datarobot.com/trial/.)
2. Check if `DATAROBOT_ENDPOINT` env var is set. If not, ask the user (default: `https://app.datarobot.com/api/v2`).
3. Derive `DATAROBOT_OTEL_ENDPOINT` automatically: if `DATAROBOT_ENDPOINT` ends with `/api/v2`, strip it and append `/otel` (e.g., `https://app.datarobot.com/api/v2` → `https://app.datarobot.com/otel`).
4. **Determine the telemetry target (Use Case)** — this is the primary entity, and works the same whether the agent was built on DataRobot or elsewhere. Only **collect** the choice here; do **not** run any script or create/validate anything yet — that happens once in Step 4, after the user approves the plan (running it here risks creating a Use Case the user never approved, and a duplicate when Step 4 runs).
   - Ask the user for their **Use Case ID**. DataRobot users typically already organize work in a Use Case.
   - If they don't have one (a brand-new or externally-built project), **offer to create one**. Ask only for a name; the description is auto-generated.
   - Record the choice (existing Use Case ID, or the name for a new one) to use in Step 4. The `create_use_case.py` helper will resolve it to an entity ID of the form `experiment_container-<use_case_id>` at execution time.
5. Check if the `datarobot` Python SDK is available. If not, install it: `pip install datarobot`.
6. Check if OTel packages are already in the project's dependencies.

**Security note:** Never ask the user to paste an API token into chat, and never echo tokens or `.env` contents into transcripts or logs. Collect the token only via the project `.env` file (the user edits the file directly) and read it from there; keep `.env` gitignored. If credentials are accidentally exposed, rotate them immediately.

### Step 3: Present Plan

Tell the user what you detected and present the changes you will make:
- Framework detected (or generic Python)
- Existing OTel setup found (if any)
- New dependencies to add
- New files to create (`dr_otel_config.py`, and optionally `dr_agent_metrics.py` for frameworks with custom metrics)
- Existing files to modify (agent entrypoint, dependency file)
- Telemetry target: enter an existing Use Case ID, or if user does not have one, generate a net new Use Case container and ID for user. Only list a shell deployment in the plan if the user explicitly asked for deployment-level monitoring; if they chose a Use Case, do not mention or ask about a deployment.

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

5. **Resolve the Use Case telemetry target** (primary entity). This is the **only** place the helper script runs — once, here, using the choice collected in Step 2 (never during prerequisites). Validate the user's existing Use Case, or create a net new one if they have none:
   ```bash
   set -a; source .env; set +a   # load DATAROBOT_API_TOKEN etc. from .env (not the command line)
   # Existing Use Case:
   python <skill_scripts_dir>/create_use_case.py --use-case-id <use_case_id>
   # No Use Case yet — create one (name only; description auto-generated):
   python <skill_scripts_dir>/create_use_case.py --name "<project_name> Monitoring"
   ```

   It returns `entity_id` as `experiment_container-<use_case_id>` — this is the OTel entity used at runtime.

6. **(Optional) Create shell deployment** — **only if the user explicitly asks** for deployment-level monitoring (drift, etc.). If the user chose a Use Case as the target, **do not ask about or prompt for a deployment ID** — the Use Case is the complete target on its own. Skip this step entirely unless the user raised it themselves.
   ```bash
   python <skill_scripts_dir>/create_shell_deployment.py \
     --name "<project_name> Monitoring" \
     --description "OTel telemetry sink for <framework> agent"
   ```

   The script automatically enables **prediction row storage** and **automatic association ID generation** on the deployment. If created, its `deployment-<id>` entity can be used as the target instead of the Use Case.

7. **Report results**: Write the resolved non-secret runtime vars into the project `.env` — never print the token. Confirm the Use Case ID (and deployment ID, if created):
   ```bash
   # appended to .env (DATAROBOT_API_TOKEN already present there; do not echo it):
   DATAROBOT_ENTITY_ID=experiment_container-<use_case_id>
   DATAROBOT_OTEL_ENDPOINT=<otel_endpoint>
   ```

### Step 5: Verify & Provide Runtime Instructions

1. Optionally run the verification script (loads credentials from `.env`; don't put the token on the command line):
   ```bash
   set -a; source .env; set +a
   python <skill_scripts_dir>/verify_otel_connection.py
   ```

2. Provide the user with the env vars to set in their runtime environment:
   - `DATAROBOT_API_TOKEN` — DataRobot API key
   - `DATAROBOT_ENTITY_ID` — `experiment_container-<use_case_id>` (Use Case target; or `deployment-<id>` if a shell deployment was created instead)
   - `DATAROBOT_OTEL_ENDPOINT` — `{DATAROBOT_ENDPOINT}/otel`

3. Explain how to view the telemetry. For a Use Case target, use the `dr` CLI's `xp`
   plugin (works in a local terminal or DataRobot Codespaces); this is the `view_command`
   returned by `create_use_case.py`:
   ```bash
   dr plugin install xp                                   # one-time
   dr xp --entity-id <use_case_id> --enable-logs --enable-metrics
   #     ^ the BARE use_case_id, NOT the experiment_container- prefixed form
   ```
   Then open the local panel at `http://127.0.0.1:8090`. You'll see:
   - **Tracing**: Span hierarchy (agent orchestration, LLM calls, tool calls)
   - **Logs**: Structured logs correlated with traces via traceId
   - **Metrics**: Custom metrics (request count, latency, LLM calls, tool calls)

## Generic OTel Configuration Pattern

Generate a `dr_otel_config.py` with a `configure_otel()` function that the project calls at startup, before any agent code runs. The **full annotated template lives in `reference/dr_otel_config.md` — read it before generating code.** Framework-specific files in `frameworks/` layer additional setup on top.

**Critical rules:**
1. Always pass `endpoint=` and `headers=` directly to exporters — NEVER use `OTEL_EXPORTER_OTLP_*` env vars (some frameworks detect these and create conflicting providers)
2. Be additive — add DataRobot as an additional span processor to any existing TracerProvider, don't replace it
3. Use `SimpleSpanProcessor` (not Batch) to avoid flush-before-shutdown issues
4. Use DELTA temporality for metrics (required by DataRobot)

**Provider initialization order:** some frameworks override the global TracerProvider at startup (notably Google ADK), which drops the DataRobot exporter. The additive pattern and per-framework workarounds (e.g. lazy injection via callbacks) are covered in `reference/dr_otel_config.md` and the framework reference files — always check them.

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

### create_use_case.py

Resolves the **primary** telemetry target: validates an existing Use Case, or creates a net new one when the user has none.

```bash
# Existing Use Case:
python <scripts_dir>/create_use_case.py --use-case-id <use_case_id>
# Create new (name only; description auto-generated):
python <scripts_dir>/create_use_case.py --name "My Agent Monitoring"
```

Requires env vars: `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT`

Returns JSON:
```json
{
  "use_case_id": "6123abc",
  "entity_id": "experiment_container-6123abc",
  "otel_endpoint": "https://app.datarobot.com/otel",
  "view_command": "dr xp --entity-id 6123abc --enable-logs --enable-metrics"
}
```

### create_shell_deployment.py

**Optional.** Creates a shell deployment in DataRobot as a telemetry routing target, for users who also want deployment-level monitoring.

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
| `DATAROBOT_ENTITY_ID` format error | Missing entity-type prefix | Must be `experiment_container-<use_case_id>` (Use Case) or `deployment-<id>`, not just `<id>` |

## Resources

- [DataRobot Model Monitoring Documentation](https://docs.datarobot.com/en/docs/mlops/monitor/index.html)
- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/)
- [OpenTelemetry OTLP Exporter](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html)
