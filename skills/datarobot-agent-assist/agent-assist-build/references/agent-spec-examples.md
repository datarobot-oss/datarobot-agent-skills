# agent_spec.md Examples

## Example 1: Weather Agent (Simple)

```yaml
model: anthropic/claude-3-5-haiku-20241022
system_prompt: You are a helpful weather assistant that provides current weather conditions
  for any location worldwide. When a user asks about weather, search for current weather
  information and present the results in a clear, conversational way. Focus on current
  conditions like temperature, weather description, and other relevant details.
tools:
  - function_name: search_weather
    inputs:
      - arg_name: location
        type: str
    out:
      - arg_name: search_results
        type: str
    auth_spec:
      service_name: Perplexity API
      auth_method: api_key
examples:
  - What's the weather like in New York?
  - How's the weather in Tokyo today?
  - Current conditions in London
frontend:
  type: chat
```

---

## Example 2: Multi-tool Research Agent (with Auth)

```yaml
model: anthropic/claude-sonnet-4-5-20250929
system_prompt: You are a research assistant that helps users find and summarize
  information from internal documents and the web. Always cite your sources.
tools:
  - function_name: search_internal_docs
    inputs:
      - arg_name: query
        type: str
      - arg_name: top_k
        type: int
    out:
      - arg_name: documents
        type: list
        object_schema: "list of {title: str, content: str, url: str}"
    auth_spec:
      service_name: Internal Knowledge Base API
      auth_method: bearer_token
  - function_name: web_search
    inputs:
      - arg_name: query
        type: str
    out:
      - arg_name: results
        type: str
examples:
  - Find recent papers on LLM hallucination
  - What does our internal policy say about data retention?
  - Summarize the latest news on AI regulation
frontend:
  type: chat
```

---

## Example 3: Multi-page Dashboard Agent

```yaml
model: google/gemini-2.5-pro-preview-05-06
system_prompt: You are a sales analytics assistant. Help users understand their
  pipeline, forecast revenue, and identify at-risk deals. Always ground your
  answers in the data returned by tools.
tools:
  - function_name: get_pipeline_data
    inputs:
      - arg_name: date_range
        type: str
        object_schema: "ISO 8601 date range, e.g. '2024-01-01/2024-03-31'"
    out:
      - arg_name: deals
        type: list
        object_schema: "list of {deal_id: str, stage: str, value: float, close_date: str, owner: str}"
    auth_spec:
      service_name: Salesforce CRM
      auth_method: oauth2
  - function_name: forecast_revenue
    inputs:
      - arg_name: period
        type: str
    out:
      - arg_name: forecast
        type: dict
        object_schema: "{expected: float, low: float, high: float, confidence: float}"
examples:
  - What's our Q2 pipeline look like?
  - Which deals are at risk of slipping?
  - Forecast revenue for next quarter
frontend:
  type: multi-page
  pages:
    - "Pipeline Overview - shows all deals by stage with filtering"
    - "Revenue Forecast - charts expected vs actual with confidence bands"
    - "At-Risk Deals - highlights deals with low probability or stalled activity"
  requirements: "Charts should use a dark theme. Pipeline table must be sortable and filterable by owner and stage."
```

---

## Auth Method Reference

| `auth_method` | When to use |
|---|---|
| `api_key` | Static key passed in header or query param (e.g. OpenAI, Perplexity, SendGrid) |
| `oauth2` | User-delegated access with token refresh (e.g. Salesforce, Google, GitHub) |
| `basic_auth` | Username + password (e.g. legacy internal APIs) |
| `bearer_token` | Static bearer token (e.g. DataRobot API, internal services) |
| `service_account` | Non-human identity with key file or IAM role (e.g. GCP, AWS) |
| `other` | Anything that doesn't fit the above |

## Frontend Type Reference

| `type` | When to use |
|---|---|
| `chat` | Default — single chat window, no additional pages needed |
| `multi-page` | Multiple distinct pages (dashboard tabs, admin panel, etc.) |
| `custom` | Fully custom UI that requires bespoke layout beyond pages |
