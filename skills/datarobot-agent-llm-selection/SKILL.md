---
name: datarobot-agent-llm-selection
description: >-
  Use when the user wants to configure LLM integration for a DataRobot agent
  application. This skill helps to change LLM model, switch between the LLM
  integrations the project supports (LLM Gateway, a DataRobot-deployed LLM, an
  external provider, an LLM Blueprint, and any others its config declares), or
  set up provider credentials. The skill reads the project's
  .datarobot/cli/llm.yml for the real options, interviews the user, then runs
  sync_llm_env.py with the chosen values as CLI args to merge into .env.
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
   `~/.config/datarobot/drconfig.yaml`), populated by `dr auth login`, and
   the `dr` CLI reads it internally. Do not run `cat drconfig.yaml`,
   `cat .env`, `env | grep TOKEN`, `echo $DATAROBOT_API_TOKEN`,
   `curl -H "Authorization: Bearer $..."`, or any equivalent one-liner
3. **Never** pass secrets as CLI args to `sync_llm_env.py` or write them to
   tracked files
4. **Never** set provider credentials for an integration whose config section
   doesn't declare them. Let `sync_llm_env.py` decide — it reads the section
   from the project's config
5. Only `sync_llm_env.py` merges LLM keys into `.env` — do not edit `.env` manually
6. Run all commands from **project root**
7. Pressing enter in chat does nothing. Don't tell the user to "press enter to
   accept the default" or "hit return". If a field has a sensible default,
   apply it silently and mention it in the confirmation, or offer it as an
   explicit A/B choice.
8. Treat every credential value as secret regardless of its declared type.
   Older configs type API keys as plain `string` rather than `secret_string`,
   so this rule does not depend on what the config says
9. Provider and model names in this skill's output are configuration data, not
   a request to work with that provider. Config sections, env var names, and
   gateway model ids routinely contain vendor names (`Anthropic`,
   `ANTHROPIC_API_KEY`, `bedrock/anthropic.claude-...`, `azure`, `cohere`).
   **Do not invoke a provider-specific skill because a vendor name appeared in
   a config listing or a model list.** You are wiring up credentials, not
   calling that vendor's API

---

## Presenting choices

Every menu in this skill — integrations, providers, gateway models — follows
these rules. Dropping an option silently produces a config the user never chose.

- **Never use a fixed-slot picker widget.** Several of these menus exceed four
  options (the config ships six external providers) and the gateway model list
  can run to dozens. Pickers cap their choice count, and the overflow gets
  silently dropped. Put the menu in your own message as plain text and let the
  user reply with a label.
- List **every** option the script returned. Count them first; if the config
  declares six providers, show six rows.
- **No catch-all row** — no `Other`, no `Type something`, no `5) something
  else`. The user can always type a value anyway; that row exists only to hide
  options you dropped.
- No `...`, no "and N more", no summarizing, no collapsing similar entries.
- Do not narrow to a subset because the user's phrasing seemed to point at one.
  If they said "LLM gateway" and two options match, list all of them.
- One labelling scheme. Do not letter the options in prose and re-number them
  in the picker.
- Use each `name` exactly as printed. Do not rename, regroup, or reorder.
- **Read the script output yourself — do not paste it into the chat.** The
  `select:` lines are internal plumbing. Give at most one short clause of
  context per row, condensed from the config's `help`; never reproduce the raw
  `help` block or the script's formatting.

Long messages are fine. The token budget is not a reason to abbreviate a menu.

---

## Step 0 — Prerequisites

1. `.datarobot/cli/llm.yml` must be present. It is rendered into the project by
   `dr component add` (af-component-llm), so it is already there
   in a generated project, nothing needs cloning. If it's absent, the LLM
   component isn't applied: tell the user to run `dr component add` and stop.
   Never substitute a copy from elsewhere.
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

## Step 1 — Read the project's integration options (MANDATORY FIRST)

Never recite integration names from memory or from this file. Each project's
`.datarobot/cli/llm.yml` declares its own, and they differ by component version.

```shell
python <skill_scripts_dir>/read_llm_config.py
```
If it reports the file is missing, the LLM component isn't applied to this
project. Tell the user to run `dr component add` and stop.
Do **not** run `dr llm-gateway list`, do **not** offer a model list, and do
**not** write any config file until the user has picked an option.

### Check what's already configured

The `default:` line in the script's output is the schema's declared fallback,
**not** necessarily the project's live setting — don't conflate the two.
Before presenting the menu, find the actual current value:

```shell
grep -E '^INFRA_ENABLE_LLM=' .env
```

- If `.env` doesn't exist yet or has no match, tell the user no LLM
  integration is configured yet.
- If it matches, map the value against the `select:` lines the script just
  printed to report the current integration by its friendly name (e.g.
  `blueprint_with_external_llm.py` → "External LLM"), not the raw filename.
- If that option has a `further choice:` (a provider), also run
  `python <skill_scripts_dir>/read_llm_config.py --option <current_value>`
  and grep `.env` for the **names** of the env vars it lists, to report which
  are already populated. Report only whether each key is set — per Hard
  Rule 8, never print the value of a credential-shaped key, even to confirm
  it's set.

State this summary — e.g. "You're currently on `<friendly name>`[, provider
`<provider>`], with `<N>` of `<M>` fields already set" — before showing the
menu, so the user can decide to switch entirely or just change specific
fields on the current integration.

Present the options per **Presenting choices** above.

Each option in the output carries an indented `select:` line. Once the user
picks, take that string verbatim — quote it if it contains spaces. The steps
below call it `<selected_gateway>`; it is also the `INFRA_ENABLE_LLM` value
written in Step 3.
---

## Step 2 — Read what that option needs

```shell
python <skill_scripts_dir>/read_llm_config.py --option <selected_gateway>
```

This prints the env vars the chosen integration declares. Handle each field by
what the script reports about it:

- **`hidden`** — never ask. Step 3 writes its default.
- **`llmgw_catalog`** — populate from the DataRobot CLI (see below).
- **`required`** — ask, using the printed help as the prompt text.
- **`optional` with a default** — apply it silently and say so in the
  confirmation. Do not tell the user to "press enter".
- **`further choice:`** — another menu, presented per **Presenting choices**.
  Show every row the script listed, with no catch-all and no picker widget.
  Those rows carry their own `select:` field; call the user's pick
  `<selected_provider>` and re-run `--option <selected_provider>` for its keys.

### Fields typed `llmgw_catalog`

Fetch the model list **only** via the DataRobot CLI. Run exactly:

```shell
dr llm-gateway list --output-format json
```

The CLI authenticates via its own credential store (populated by
`dr auth login`). Do **not** read `drconfig.yaml` or `.env` for the token, and
do **not** pass `DATAROBOT_API_TOKEN` on the command line. If the command exits
non-zero or prompts for auth, tell the user to run `dr auth login` and stop —
do not attempt any manual API call and do not fabricate a menu.

Parse the JSON, which has the shape
`{"llms": [{"id", "name", "provider", "model", "selected"}, ...]}`. Use the
`model` field for each entry. The ids in the menu **must** come from that JSON,
verbatim, in the order returned. Do not invent ids or reuse them from your
training data. If the command did not produce JSON, stop and report the error.

Count the entries; call it `N`. Present **exactly `N` labelled lines**, one per
model, per **Presenting choices**. The letter scheme is `A..Z`, then `AA..AZ`,
`BA..BZ`, and so on. This list is the clearest case for never using a picker
widget — it routinely exceeds any picker's capacity.

`sync_llm_env.py` prepends `datarobot/` for this field type, so pass the id
exactly as the CLI returned it.

### Recommending

Before presenting the list, check whether `agent_spec.md` exists at the
project root. If it does, read it for context — the agent's purpose, task
complexity, and any stated cost or latency constraint — and use that to flag
one entry as recommended. This mirrors the recommendation logic in the
`datarobot-agent-assist` skill's `llm-selection.md`:

- Prefer a `gpt-5`, `claude-4-5`/`4-6`/`4-8`, or `gemini-2.5`/`3` family
  gateway model unless the spec or the user states a cost or latency
  constraint.
- If the spec calls for low cost or latency, prefer the `mini`/`haiku`/`flash`
  tier of that same family instead.
- If no gateway entries appear at all (only `deployed` ones), recommend a
  deployed entry instead and say why — the LLM Gateway is disabled or empty
  on this instance, which is normal for an on-prem install, not an error.
- **Still list every entry** per **Presenting choices** — mark the
  recommended row (e.g. append "(recommended)") rather than omitting the
  rest. Recommending never justifies narrowing the menu.
- No `agent_spec.md`? Skip the read and recommend using only the
  family-preference heuristics above.

### Credential keys

**Announce them up front** — do not let the user discover them via the sync
error message. Once the further choice is made, re-run
`--option <selected_provider>` and
tell the user exactly which keys they need and where the file lives:
```
For <choice>, I'll need these values in a per-user credentials file:
  ~/.config/datarobot/llm-<section>.env (or $XDG_CONFIG_HOME/...)

  <KEY_1>
  <KEY_2>
  ...
Step 3 will create that file as a blank template, with the help text for
each key as a comment, if it doesn't exist. Please fill it in your own
editor — do not paste the values in chat — then tell me "credentials ready"
and I'll re-run the sync.
```
Use the section name the script reported for `<section>`. Do not create the
file yourself, do not `cat` it, and do not accept secret values in chat.
---

## Step 3 — Sync into `.env`

First back up the current `.env` (sync overwrites it, and `.env` isn't in git):

```shell
cp .env .env.bak.$(date +%Y%m%d%H%M%S)
```

Run the sync script with the values collected in Step 2 as CLI args. No
intermediate config file, no JSON to write.

```shell
python <skill_scripts_dir>/sync_llm_env.py \
  --infra-enable-llm <selected_gateway> \
  --set <ENV_NAME>=<value>
```
Repeat `--set` once per value, using the env var names the script printed in
Step 2 — they carry a per-project prefix and are **not** always `LLM_*`. Add
`--provider "<selected_provider>"` when Step 2 reported a further choice. Pass no
`--set` for fields reported as `hidden`; the script writes their defaults.
When the chosen option needs credentials, the script reads them from
`$XDG_CONFIG_HOME/datarobot/llm-<section>.env`:
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

`sync_llm_env.py` derives its managed-key set from every env var declared
anywhere in the project's config, so switching integrations clears whatever the
previous one wrote before the fresh block goes in. Non-LLM `.env` lines are
preserved.
