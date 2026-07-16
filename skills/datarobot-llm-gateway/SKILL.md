---
name: datarobot-llm-gateway
description: >-
  Use when the user wants to configure LLM integration for a DataRobot agent
  application. This skill helps to change LLM model, switch between LLM Gateway / deployed /
  external / blueprint-gateway, or set up provider credentials. The skill
  interviews the user, then runs sync_llm_env.py with the chosen values as
  CLI args to merge into .env. 
---

# DataRobot LLM gateway configuration

Configure LLM integration **without hand-editing `.env`**. The skill drives
`sync_llm_env.py` with the user's answers as CLI arguments.

## Resolve script path once per session

`<skill_scripts_dir>` = the `scripts/` subdirectory of the directory containing this `SKILL.md`.

```shell
ls <skill_scripts_dir>/sync_llm_env.py
```

## Hard rules

1. **Never** ask the user to paste API keys or `DATAROBOT_API_TOKEN` in chat
2. **Never** read, copy, echo, or pass `DATAROBOT_API_TOKEN` yourself. The
   token lives in `$XDG_CONFIG_HOME/datarobot/drconfig.yaml` (default
   `~/.config/datarobot/drconfig.yaml`), populated by `dr auth login`. Only
   `list_gateway_models.py` reads that file; it never emits the token to
   stdout. Do not run `cat drconfig.yaml`, `cat .env`, `env | grep TOKEN`,
   `echo $DATAROBOT_API_TOKEN`, `curl -H "Authorization: Bearer $..."`, or
   any equivalent one-liner
3. **Never** pass secrets as CLI args to `sync_llm_env.py` or write them to
   tracked files
4. **Never** set provider credentials (`AWS_*`, `OPENAI_*`, etc.) for `gateway` or `blueprint-gateway`
5. Only `sync_llm_env.py` merges LLM keys into `.env` — do not edit `.env` manually
6. Run all commands from **project root**
7. Pressing enter in chat does nothing. Don't tell the user to "press enter to
   accept the default" or "hit return". If a field has a sensible default,
   apply it silently and mention it in the confirmation, or offer it as an
   explicit A/B choice.

---

## Step 0 — Prerequisites

1. Project root must exist (`.datarobot/cli/llm.yml` present).
2. **DataRobot auth** — check that
   `$XDG_CONFIG_HOME/datarobot/drconfig.yaml` (default
   `~/.config/datarobot/drconfig.yaml`) exists. If it doesn't, tell the user
   to run `dr auth login` (browser-based flow) and stop until they confirm
   they're signed in. Do **not** cat the file to inspect its contents.
3. Check if `.env` exist in the project:
   - If `.env` is missing `cp .env.template .env`. That gives the base variables (`DATAROBOT_*`,
     `PULUMI_*`, etc.) many are blank, it will be filled later. But the sync in Step 3
     only needs the file to exist.
   - If both `.env` and no `.env.template` are missing, tell the user they're not in
     a DataRobot agent project root and stop.

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
Choose your LLM integration.

  - For the simplest setup, pick LLM Gateway.
  - If you already have a custom LLM deployed on DataRobot with a
    deployment ID, pick DataRobot Deployed LLM (this sets
    USE_DATAROBOT_LLM_GATEWAY=0).
  - If you want to use your own LLM provider credentials instead of the
    LLM Gateway (e.g. Azure OpenAI, AWS Bedrock, GCP VertexAI, Anthropic,
    Cohere, TogetherAI), pick External LLM.
  - If you need full DataRobot governance and monitoring with LLM
    Blueprint support, pick LLM Blueprint with LLM Gateway. This is the most
    production-ready option.

Which LLM integration would you like? Reply with A, B, C, or D
(or the keyword: gateway / deployed / external / blueprint-gateway):

  A) gateway            — DataRobot-managed LLM Gateway (recommended)
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

   The script reads `endpoint` and `token` from
   `$XDG_CONFIG_HOME/datarobot/drconfig.yaml` (populated by `dr auth login`).
   Do **not** read that file yourself, do **not** read `.env` for the token,
   and do **not** pass `DATAROBOT_API_TOKEN` on the command line.

   If the script exits non-zero with a "credentials not found" message, tell
   the user to run `dr auth login` and stop — do not attempt any manual API
   call and do not fabricate a menu.

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

3. Wait for the letter (or a full model id typed by the user), then use that
   id as `--llm-model` in Step 3. The sync script normalizes to a `datarobot/`
   prefix if the user omits it.
4. For `blueprint-gateway` only, offer an explicit A/B choice for
   `--llm-llm-id`:

   ```
   Which LLM blueprint id?
     A) azure-openai-gpt-5-mini (recommended)
     B) type a different id
   ```

   Skip this altogether if the user hasn't shown interest in tuning it.

### `deployed`

1. Ask: `llm_deployment_id` (24 lowercase hex characters). If the user's
   answer doesn't match `^[0-9a-f]{24}$`, re-ask.
2. For `llm_model`, use `datarobot/datarobot-deployed-llm` unless the user
   explicitly specifies something else. Do not ask them to "press enter to
   accept" — just apply it and mention it in the sync confirmation.

### `external`

1. List providers as a lettered menu and wait for the user's reply:

   ```
   Which external provider?
     A) azure
     B) bedrock
     C) vertexai
     D) anthropic
     E) cohere
     F) togetherai
   ```

   Accept the letter or the keyword. Re-ask if the reply doesn't match.
2. Ask for `llm_model`. For Azure, offer an explicit A/B choice:

   ```
   Which default llm model?
     A) azure-openai-gpt-5-mini (recommended)
     B) type a different model id
   ```

   For other providers, ask the user to type the model id — there is no
   sensible default to offer.
3. **Announce the credential requirements up front** — do not let the user
   discover them via the sync error message. Once you know the provider,
   tell the user exactly which keys they'll need to fill in and where the
   file lives.

   Per-provider required keys:

   | Provider | Required env vars |
   |----------|-------------------|
   | `azure` | `OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_API_DEPLOYMENT_ID`, `OPENAI_API_VERSION` |
   | `bedrock` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME` |
   | `vertexai` | `VERTEXAI_APPLICATION_CREDENTIALS`, `VERTEXAI_SERVICE_ACCOUNT` |
   | `anthropic` | `ANTHROPIC_API_KEY` |
   | `cohere` | `COHERE_API_KEY` |
   | `togetherai` | `TOGETHERAI_API_KEY` |

   Post this to the user (substitute the real provider + keys):

   ```
   For <provider>, I'll need these values in a per-user credentials file:
     ~/.config/datarobot/llm-<provider>.env (or $XDG_CONFIG_HOME/...)

     <KEY_1>
     <KEY_2>
     ...

   Next step (Step 3) will create that file as a blank template if it
   doesn't exist. Please fill it in your own editor — do not paste the
   values in chat — then tell me "credentials ready" and I'll re-run the
   sync.
   ```

   Do not create the file yourself, do not `cat` it, and do not accept
   secret values in chat.

---

## Step 3 — Sync into `.env`

Run the sync script with the values collected in Step 2 as CLI args. No
intermediate config file, no JSON to write. Examples for each mode:

**Gateway:**

```shell
python <skill_scripts_dir>/sync_llm_env.py \
  --integration gateway \
  --llm-model datarobot/azure/o4-mini
```

**Blueprint-gateway** (omit `--llm-llm-id` unless the user set one):

```shell
python <skill_scripts_dir>/sync_llm_env.py \
  --integration blueprint-gateway \
  --llm-model datarobot/azure/o4-mini \
  --llm-llm-id azure-openai-gpt-5-mini
```

**Deployed** (omit `--llm-model` to use the `datarobot/datarobot-deployed-llm`
default):

```shell
python <skill_scripts_dir>/sync_llm_env.py \
  --integration deployed \
  --llm-deployment-id 6510c7b7c4f3f9407e24a849
```

**External:**

```shell
python <skill_scripts_dir>/sync_llm_env.py \
  --integration external \
  --external-provider azure \
  --llm-model azure-openai-gpt-5-mini
```

For external mode, the script also reads provider credentials from
`$XDG_CONFIG_HOME/datarobot/llm-<provider>.env`:

- **If the file doesn't exist**, the script writes a blank template there
  and exits with the path plus the required key list. Relay that verbatim
  to the user, tell them to fill it in their own editor, then re-run the
  same command. Do not offer to create the file for them and do not accept
  values in chat.
- **If the file exists but is incomplete**, the script prints the missing
  keys and exits. Same instruction: user edits, then re-runs.
- **If the file is complete**, the sync merges the credentials into `.env`
  in one shot.

---

## Step 4 — Validate and hand off

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
