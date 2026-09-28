---
name: datarobot-agent-assist-deploy-workload
description: Use when an agent assist user wants to deploy their agent, put it on DataRobot, get a link to it, or share it with others, and the agent can run as a single container. Users usually just say "deploy" or "deploy to DataRobot" and won't mention containers, workloads or the CLI.
---

# Agent Assist — Deploy via Workload API

This is the path for agents that fit in one container. The agent, its tools, its API and its UI run in one process on one port, and `dr workload up` builds and deploys it. Anything that doesn't fit in one container is deployed as a custom application with Pulumi, which deploys the agent, MCP server and web app separately.

The user may not be technical. Do the technical steps yourself and explain what's happening in plain words. Don't ask them for ids, YAML or commands when you can find or run them yourself.

Start from an implemented agent: a project built from the agent template (option 2), or any single Python project. `<target_dir>` is the directory that holds `agent_spec.md` and the agent code. If there is no spec, send the user to design first.

## 1. Choose the deploy path

If agent assist hasn't already picked this path, read and follow [references/deploy-path.md](references/deploy-path.md). Continue here only if it picks the Workload API.

## 2. Check the CLI

1. `dr --version`. If missing, run `curl https://cli.datarobot.com/install | sh`.
2. `dr self update --force`. Always run it. Don't try to judge whether the installed version is new enough.
3. `dr auth check`. If it fails, run `dr auth login`. It opens a browser. Tell the user: "A DataRobot sign-in page just opened. Sign in there and come back."
4. `dr workload up` and `dr workload config` are still behind a CLI feature flag. Put `DATAROBOT_CLI_FEATURE_WORKLOAD=true` in front of every `dr workload up` and `dr workload config` call. Each shell call is a new shell, so an earlier export doesn't carry over. The commands in this skill already have it; copy them as written.
5. `DATAROBOT_CLI_FEATURE_WORKLOAD=true dr workload up --help`. If it says unknown command, the update didn't take. Don't ask the user to fix it. Use `references/deploy-fallback.md` when you get to section 4.

## 3. Configure the deploy (once)

First read and follow `references/app-contract.md`. It checks that the code in `<target_dir>` meets what the deploy needs and fixes what doesn't. Don't configure until it passes.

`dr workload config` writes `.datarobot.yaml`, the deploy definition. It lives in the repo with the code. There's no terminal here, so every answer is a flag:

```bash
DATAROBOT_CLI_FEATURE_WORKLOAD=true dr workload config --yes --skip-env \
  --name <agent-name> --type agent \
  --build-mode generated \
  --execution-environment "[DataRobot] Python 3.12 Applications Base" \
  --entrypoint "uvicorn <entry point> --host 0.0.0.0 --port 8080" \
  --port 8080 --health /healthz
```

`--skip-env` keeps the local `.env` out of the manifest. That file holds the user's own API token, and the deployed agent should use its own key. `--type` can't be changed later. If the execution environment isn't found, look one up yourself: `GET /executionEnvironments/?searchFor=Python&limit=10`. If that returns 403, the user needs their admin. Give them a message to send: "Which Python 3.12 execution environment should I use to deploy an agent with the Workload API?" If config says a manifest already exists, don't delete it. Edit `.datarobot.yaml` instead.

Add the environment to the primary container (`artifact`, `spec`, `containerGroups`, `containers`) in `.datarobot.yaml`:

```yaml
environmentVars:
  - name: DATAROBOT_ENDPOINT
    value: <endpoint>   # eval "$(dr auth export)"; echo "$DATAROBOT_ENDPOINT"
  - name: DATAROBOT_API_TOKEN
    source: api-key                           # platform injects a key for this workload
  - name: SOME_TOOL_API_KEY
    source: dr-credential
    drCredentialId: <credential id>
    key: apiToken
```

Store each tool secret as a DataRobot credential yourself once the user has put it in `.env`. Follow `references/tool-secrets.md`. Don't ask the user to create credentials or find ids.

## 4. Deploy

```bash
DATAROBOT_CLI_FEATURE_WORKLOAD=true dr workload up --yes --output-format json
```

Tell the user it takes a couple of minutes. The first run creates the artifact, uploads the code, builds the image and starts the workload. Don't pass `--detach`; wait for it. The JSON has `workloadId`, `endpoint` and `status`.

`up` writes the workload id into `.datarobot.yaml`. That file is how the next deploy finds the same agent. If `<target_dir>` is a git repo, commit it yourself. Tell the user not to delete it.

Redeploy with the same command. It only applies what changed. Env var, port or probe changes take seconds and don't rebuild. Code and dependency changes rebuild. Use `--force-build` only when a rebuild is needed and nothing changed, for example the image is gone from the registry.

`up` only manages fields that `.datarobot.yaml` names, and it puts those back if someone changed them in the UI. Make changes in the file, not the UI. If the user says they changed a setting in DataRobot, run `--dry-run` first and tell them in plain words what would be changed back.

If the workload is locked (see 6), ask before every `up`: "This will update the agent people are using now. Go ahead?"

If `up` or `config` fails, handle it yourself without asking the user:

- `unknown command`: the CLI flag was missing. Rerun with `DATAROBOT_CLI_FEATURE_WORKLOAD=true` in front. If it's still unknown with the flag, go straight to the fallback below.
- 403 `Workload API is disabled in feature flags`, from any call: the Workload API is off for the account. Don't retry and don't use the fallback, which calls the same API. Switch to Pulumi as in [references/deploy-path.md](references/deploy-path.md) and tell the user why.
- Anything else that isn't about the app: read and follow `references/deploy-fallback.md`. Keep the app as it is. Only the deploy steps change.

## 5. Check it answers

`up` succeeding means the container is healthy, not that the agent works. `/healthz` never calls the LLM. Check two things:

```bash
eval "$(dr auth export)"   # never print the token
curl -sS -o /dev/null -w "%{http_code}\n" "<endpoint>/healthz"   # no token: expect 401
```

A 200 means anyone with the link can use the agent, because the app has no sign-in of its own. Don't share the link. Tell the user: "Your agent is reachable without signing in to DataRobot. Please check with your DataRobot admin before sharing it."

Then send one example from the spec's `examples` to the chat API with `-H "Authorization: Bearer $DATAROBOT_API_TOKEN"`. If it fails, check `dr workload logs --level error`. It's usually the env block from section 3. Then give the user the link and tell them to open it in a browser where they're signed in to DataRobot.

If something breaks later:

- Assets or API calls 404: a URL is missing the prefix.
- 401 and the request isn't in the logs: the frontend sent `Authorization`, or the browser has no DataRobot session.
- Empty logs don't mean healthy. Some clusters don't collect them. Use `dr workload status`, then the `datarobot-workload-api` skill, section 2.

## 6. Before you hand it over

Ask the user about these in plain words and let them decide.

- Keeping it on. Say: "Right now your agent turns off 8 hours after it starts, even if people are using it. Want me to make it permanent? Once I do, every future update replaces it without downtime. This can't be undone." If yes, run `DATAROBOT_CLI_FEATURE_WORKLOAD=true dr workload up --yes --lock`.
- Sharing. Ask who should have access, by DataRobot username or email. Then do it yourself: `GET /workloads/{id}/sharedRoles`, add the new people, and `PATCH /workloads/{id}/sharedRoles` with the full list. The PATCH replaces the whole list, so keep the owner in it or they lose access. Roles are uppercase: `OWNER`, `USER`, `CONSUMER`. Use `CONSUMER` for people who only use the agent. If the body is rejected, the 422 names the expected shape. Tell the user that the people they added need to be signed in to DataRobot to open the link.
- Removing it. Say: "If you want it gone later, just tell me." Then `dr workload stop` and `dr workload delete`.
