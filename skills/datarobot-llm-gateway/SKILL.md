---
name: datarobot-llm-gateway
description: >-
  Use when the user wants to configure LLM integration for a DataRobot agent
  application — change LLM model, switch between LLM Gateway / deployed /
  external / blueprint-gateway, or set up provider credentials. The skill
  interviews the user step by step, writes .datarobot/llm-config.json, plans
  .secrets/ for external providers, then runs sync_llm_env.py to merge into
  .env. Never paste secrets in chat.
---

# DataRobot LLM gateway configuration (spec + sync)

Configure LLM integration **without hand-editing `.env`**. The skill writes structured
config; `sync_llm_env.py` merges into `.env`.

## Resolve script path once per session

`<skill_scripts_dir>` = the `scripts/` subdirectory of the directory containing this `SKILL.md`.

```shell
ls <skill_scripts_dir>/sync_llm_env.py
```

## Hard rules

1. **Never** ask the user to paste API keys or `DATAROBOT_API_TOKEN` in chat
2. **Never** read, copy, echo, or pass `DATAROBOT_API_TOKEN` yourself. Only the
   bundled scripts touch the token; they read it from `.env` / environment and
   never emit it to stdout. Do not run `cat .env`, `env | grep TOKEN`,
   `echo $DATAROBOT_API_TOKEN`, `curl -H "Authorization: Bearer $..."`, or any
   equivalent one-liner
3. **Never** write secrets into `.datarobot/llm-config.json` or tracked files
4. **Never** set provider credentials (`AWS_*`, `OPENAI_*`, etc.) for `gateway` or `blueprint-gateway`
5. Only `sync_llm_env.py` merges LLM keys into `.env` — do not edit `.env` manually
6. Run all commands from **project root**
7. After sync: `dr dotenv validate` then remind user: `dr task run infra:up-yes`

---

## Step 0 — Prerequisites

1. Project root must exist (`.datarobot/cli/llm.yml` present)
2. If no `.env`: tell user to run `dr dotenv setup --if-needed` or `dr start` first (base vars only)
3. DataRobot auth: `dr dotenv update` (do not set `DATAROBOT_API_TOKEN` via this skill)

---

## Step 1 — Integration mode (ASK THIS FIRST — MANDATORY)

**Before doing anything else in this skill**, ask the user which integration
mode they want. The value must be one of exactly these four:
`gateway`, `deployed`, `external`, `blueprint-gateway`.

Do **not** run `list_gateway_models.py`, do **not** offer a model list, and
do **not** write any config file until this question has been answered.

Post the menu below verbatim (letters + integration keyword + short blurb) and
wait for the user's reply:

```
Which LLM integration would you like? Pick one:
  A) gateway            — DataRobot-managed LLM Gateway (recommended default)
  B) deployed           — an LLM already deployed on DataRobot
  C) external           — bring your own provider (Azure, Bedrock, Vertex, Anthropic, …)
  D) blueprint-gateway  — LLM Blueprint routed through the LLM Gateway
```

Map the user's answer to the `integration` value and the corresponding
`INFRA_ENABLE_LLM` script:

| Choice | `integration` | `INFRA_ENABLE_LLM` |
|--------|---------------|---------------------|
| A | `gateway` | `gateway_direct.py` |
| B | `deployed` | `deployed_llm.py` |
| C | `external` | `blueprint_with_external_llm.py` |
| D | `blueprint-gateway` | `blueprint_with_llm_gateway.py` |

Accept the letter (`A`–`D`) or the integration keyword typed out
(`gateway` / `deployed` / `external` / `blueprint-gateway`). If the user's
reply is anything else, re-ask the question — do not guess.

---

## Step 2 — Mode-specific questions

### `gateway` or `blueprint-gateway`

1. Fetch the model list **only** via the bundled script. There is **no** `dr`
   CLI command to list gateway models — do not attempt `dr get-llms`,
   `dr list-llms`, `dr llm list`, `dr genai`, or any other variant. Run
   exactly:

   ```shell
   python <skill_scripts_dir>/list_gateway_models.py
   ```

   The token stays inside the script — do **not** read `.env` yourself or
   pass `DATAROBOT_API_TOKEN` on the command line.

   If the script exits non-zero with a "TOKEN not set" or "ENDPOINT not set"
   message, tell the user to run `dr dotenv update` and stop — do not attempt
   any manual API call and do not fabricate a menu.

2. Parse the JSON returned in step 1. The model ids in the menu you show the
   user **must** come from that JSON, verbatim, in the order returned. Do not
   invent model ids. Do not reuse ids from your training data or from the
   example below. If step 1 did not produce JSON, stop and report the error.

   Count the entries; call it `N`. Print **exactly `N` labelled lines**, one
   per model. The letter scheme is `A..Z`, then `AA..AZ`, `BA..BZ`, and so on.

   **Forbidden shortcuts** — none of these are acceptable:
   - Ending the list with `...`, `…`, or "and N more"
   - A catch-all row like `E) other`, `F) other`, `Z) other model`
   - "I'll skip the rest for brevity"
   - Summarization, grouping-family collapse, or "similar variants omitted"
   - Rendering fewer than `N` rows and telling the user to ask if they want more

   Long output is fine; the token budget for this message is not a reason to
   abbreviate.

   Format template (do **not** copy the placeholder ids — substitute the real
   ones from the JSON):

   ```
   Which model? (all N models available via the LLM Gateway)
     A) <model-id-from-json[0]>
     B) <model-id-from-json[1]>
     C) <model-id-from-json[2]>
     … one labelled row per entry until every JSON element is listed …
   ```

3. Wait for the letter (or a full model id typed by the user), then set
   `llm_model` to that id. The sync script normalizes to a `datarobot/` prefix
   if the user omits it.
4. For `blueprint-gateway` only, optional: `llm_llm_id` (default
   `azure-openai-gpt-5-mini`) — skip unless the user asks about it.
5. **Skip Step 3** (no credentials file).

### `deployed`

1. Ask: `llm_deployment_id` (24-char hex).
2. Optional: `llm_model` (default `datarobot/datarobot-deployed-llm`).
3. **Skip Step 3**.

### `external`

1. Present the provider list as a lettered menu and wait for the user's choice:

   ```
   Which external provider?
     A) azure
     B) bedrock
     C) vertexai
     D) anthropic
     E) cohere
     F) togetherai
   ```

   Map the letter back to the `external_provider` value.
2. Ask: `llm_model` (default `azure-openai-gpt-5-mini` for Azure).
3. Continue to **Step 3**.

---

## Step 3 — Credentials file plan (external only)

Show the user this plan before creating files:

```text
.secrets/llm-external.env   ← you fill provider secrets here (gitignored)
.datarobot/llm-config.json  ← non-secret LLM settings (gitignored)
.env                        ← updated by sync script only
```

Run template writer (from project root):

```shell
python <skill_scripts_dir>/sync_llm_env.py write-template \
  --provider <external_provider> \
  --output .secrets/llm-external.env
```

Tell the user:

> Open `.secrets/llm-external.env`, fill in the values, save, then reply **credentials ready**.
> Do not paste secrets in chat.

Wait for **credentials ready** before Step 5.

---

## Step 4 — Write `.datarobot/llm-config.json`

Write JSON (no secrets). Examples:

**Gateway:**

```json
{
  "integration": "gateway",
  "llm_model": "datarobot/azure/o4-mini"
}
```

**Blueprint-gateway:**

```json
{
  "integration": "blueprint-gateway",
  "llm_model": "datarobot/azure/o4-mini",
  "llm_llm_id": "azure-openai-gpt-5-mini"
}
```

**Deployed:**

```json
{
  "integration": "deployed",
  "llm_deployment_id": "6510c7b7c4f3f9407e24a849",
  "llm_model": "datarobot/datarobot-deployed-llm"
}
```

**External (Azure example):**

```json
{
  "integration": "external",
  "external_provider": "azure",
  "llm_model": "azure-openai-gpt-5-mini",
  "credentials_file": ".secrets/llm-external.env"
}
```

---

## Step 5 — Sync into `.env`

Pass `--delete-config` so the intermediate `llm-config.json` is removed once the
merge succeeds — the durable state lives in `.env` (managed block) and, for
external mode, in `.secrets/llm-external.env`:

```shell
python <skill_scripts_dir>/sync_llm_env.py sync \
  --config .datarobot/llm-config.json \
  --env-file .env \
  --delete-config
```

The script only deletes the config **after** a successful write; if the sync
fails, the config file is preserved so the user can fix and retry.

If external mode and credentials are missing or empty, the script exits with a
checklist — send user back to Step 3. In that case the config file stays in
place, so you can re-run the same command after `.secrets/llm-external.env` is
filled in.

---

## Step 6 — Validate and hand off

**`dr dotenv validate` echoes the full `.env` (including `DATAROBOT_API_TOKEN`)
to stdout.** If you run it without redirection, the token lands in the chat
transcript and must be rotated. Same risk for `dr dotenv update`, `dr task run`,
`dr run`, `cat .env`, `env | grep`, or any other command that reads `.env`.

Run validation with all output suppressed and check only the exit code:

```shell
dr dotenv validate >/dev/null 2>&1
```

- **Exit 0** → tell the user validation passed.
- **Non-zero exit** → do **not** re-run the command with output visible.
  Tell the user to run `dr dotenv validate` themselves in their own terminal
  so the error stays local.

Then tell the user (do not run these yourself — they also echo secrets):

```text
LLM configuration synced to .env.

Please run these yourself in your terminal:
  dr dotenv update          # refresh DataRobot token if needed
  dr task run infra:up-yes  # push runtime params to deployment
  dr run dev                # local test
```

---

## Stale keys

The sync script removes prior LLM-managed keys from `.env` and writes a fresh managed block
for the selected mode (e.g. clears `AWS_*` when switching to `gateway`). Non-LLM `.env`
lines are preserved.
