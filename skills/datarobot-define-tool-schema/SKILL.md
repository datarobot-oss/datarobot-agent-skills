---
name: datarobot-define-tool-schema
description: Author and validate the model-metadata.yaml inputSchema that makes a custom DataRobot deployment callable as an MCP tool. Use when a deployment exposes custom (non-chat, non-predictive) request/response shapes and needs a tool interface defined, validated, or fixed.
---

# DataRobot Define Tool Schema Skill

This skill walks you through authoring and validating the `inputSchema` field in a custom model's `model-metadata.yaml`. The schema is read by `datarobot-genai` at registration time to generate the MCP tool's callable interface. Getting it right up front prevents registration errors and malformed tool calls at runtime.

## Quick Start

Three steps to a working tool schema:

1. **Write the schema.** Open your custom model's `model-metadata.yaml` and add (or update) the `inputSchema` key. Map each part of your deployment's HTTP request to one of the four envelope properties (`path_params`, `query_params`, `data`, `json`). See the worked example below.

2. **Validate locally.** Run the bundled validator against your file before deploying:

   ```bash
   python scripts/validate_tool_schema.py model-metadata.yaml
   ```

   Exit code 0 with no printed errors means the schema is valid. Any validation errors are printed as human-readable strings — fix them and re-run.

3. **Deploy and register.** Once the validator passes, push the updated custom model to DataRobot and register the deployment as an MCP tool using the `datarobot-register-mcp-tool` skill.

## When to use this skill

Use this skill only when your deployment uses **custom I/O** — a hand-authored scoring hook or endpoint that receives an arbitrary HTTP request body and returns a custom HTTP response. This is the only case where you must write an `inputSchema` by hand.

You do NOT need this skill for:

- **Standard predictive models** (AutoML, registered models with tabular targets). DataRobot automatically generates a fallback schema of `{"data": "<CSV>"}` for these deployments — no `inputSchema` is required.
- **Agentic workflow or chat deployments** (target type `agenticworkflow`, or any deployment that supports the chat API via `supports_chat_api`). These receive an automatic OpenAI chat-style fallback at `/chat/completions`. The `datarobot-register-mcp-tool` skill handles them without any schema authoring.

If you are not sure which category your deployment falls into, check the **Target Type** shown on the deployment overview in the DataRobot UI. Alternatively, retrieve the deployment via the SDK (`dr.Deployment.get(deployment_id)`) and inspect its model info — but do not rely on a specific attribute chain; attribute paths vary across SDK versions. If the target type is `agenticworkflow` or the deployment card shows a Chat tab, skip this skill.

## The interface envelope

`datarobot-genai` reads `inputSchema` from the deployment's `/directAccess/info/` endpoint. The schema must be a JSON Schema object with **exactly four allowed top-level properties**, each mapping to a distinct part of the HTTP request sent to your scoring endpoint:

| Property | Maps to | Nesting |
|---|---|---|
| `path_params` | URL path segments (e.g. `/score/{id}`) | Flat only — all property values must be primitive types (string, number, boolean, integer) |
| `query_params` | URL query string parameters | Flat only — same primitive-only restriction |
| `data` | Form or raw request body | Nested objects allowed; leaf values must be strings |
| `json` | JSON request body | Arbitrary nesting and types allowed |

No other top-level keys are permitted in the envelope. If your deployment only uses a JSON body, define only `json` and omit the rest.

Both `path_params` and `query_params` are **flat objects**: their `properties` must contain only scalar types. A nested object or array under either of these will fail validation.

`$ref` and `$defs` are supported across all four envelope properties for reuse. Inline the definitions inside the `inputSchema` block; do not reference external files.

There is **no output schema**. The HTTP response body from your scoring hook is returned to the MCP client as-is. If your response shape needs documenting, put it in the skill's description or a separate doc.

**Runtime requirement:** `datarobot-drum >= 1.17.2` must be present in the custom model's environment. Earlier versions do not surface the `inputSchema` field to `datarobot-genai`, so the tool will not be callable.

**Empty schema behavior:** By default, `datarobot-genai` rejects a deployment whose `inputSchema` is missing or empty. To override this during development, set `MCP_SERVER_TOOL_REGISTRATION_ALLOW_EMPTY_SCHEMA=true` on the MCP server. Do not rely on this flag in production.

## Authoring an inputSchema

The `inputSchema` lives inside `model-metadata.yaml` at the top level of your custom model directory. Here is a complete example for a deployment whose scoring hook accepts a JSON body with a required `query` string and an optional integer `max_results`:

```yaml
# model-metadata.yaml
name: my-search-deployment
targetType: unstructured

inputSchema:
  type: object
  properties:
    json:
      type: object
      required:
        - query
      properties:
        query:
          type: string
          description: The search query to execute.
        max_results:
          type: integer
          description: Maximum number of results to return. Defaults to 10.
          default: 10
        filters:
          type: object
          description: Optional key/value filters applied to the result set.
          properties:
            category:
              type: string
            date_from:
              type: string
              format: date
```

This schema tells `datarobot-genai` that the MCP tool accepts a `json` body. The `query` field is required; `max_results` and `filters` are optional. The envelope has only the `json` property — `path_params`, `query_params`, and `data` are omitted because this deployment does not use them.

If your deployment also accepts a path parameter — for example, `POST /score/{tenant_id}` — add `path_params` alongside `json`:

```yaml
inputSchema:
  type: object
  properties:
    path_params:
      type: object
      required:
        - tenant_id
      properties:
        tenant_id:
          type: string
          description: Tenant identifier used to route the request.
    json:
      type: object
      required:
        - query
      properties:
        query:
          type: string
```

The following example shows `query_params` (flat, primitive values only) and a `data` body (string-primitive leaves) for a deployment that accepts a form-encoded body and URL query filters:

```yaml
inputSchema:
  type: object
  properties:
    query_params:
      type: object
      properties:
        format:
          type: string
          description: Response format, e.g. "json" or "csv".
        limit:
          type: integer
          description: Maximum number of records to return.
    data:
      type: object
      properties:
        document_id:
          type: string
          description: ID of the document to process.
        language:
          type: string
          description: BCP-47 language tag, e.g. "en-US".
```

`query_params` is flat — every property is a primitive (`string`, `integer`, `boolean`, or `number`). `data` leaf values are strings. Neither envelope may contain nested objects or arrays.

Keep `path_params` and `query_params` strictly flat. Adding a nested `object` under either will cause a validation error.

## Validating

Run the local validator before pushing your model to DataRobot. It checks all structural rules enforced by `datarobot-genai` — envelope keys, flatness constraints, type restrictions — and prints each error on its own line. Exit code 0 with no printed errors means the schema is valid.

```bash
python scripts/validate_tool_schema.py model-metadata.yaml
```

The validator also accepts a `--allow-empty` flag if you want to test a file without an `inputSchema` block (mirrors the `MCP_SERVER_TOOL_REGISTRATION_ALLOW_EMPTY_SCHEMA` server flag):

```bash
python scripts/validate_tool_schema.py model-metadata.yaml --allow-empty
```

Fix every reported error before deploying. Common mistakes: using an unknown top-level key (e.g. `body` instead of `json`), nesting an object inside `query_params`, or referencing a `$ref` that is not defined in `$defs` within the same block.

## Scripts

- `scripts/validate_tool_schema.py` — validates an `inputSchema` dict against `datarobot-genai`'s structural rules; accepts a path to `model-metadata.yaml` and an optional `--allow-empty` flag; exits non-zero and prints error strings when validation fails.
