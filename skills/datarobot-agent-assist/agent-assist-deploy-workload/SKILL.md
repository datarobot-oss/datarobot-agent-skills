---
name: datarobot-agent-assist-deploy-workload
description: Use when an agent assist user wants to deploy their agent, put it on DataRobot, get a link to it, or share it with others, the agent can run as a single container, and the project has no `infra/Pulumi.yaml`. Not for agents built from the agent template, which deploy with Pulumi through datarobot-agent-assist. Users usually just say "deploy" or "deploy to DataRobot" and won't mention containers, workloads or the CLI.
---

# Agent Assist — Deploy via Workload API

This is the path for agents that fit in one container and don't use a Pulumi infrastructure-as-code template. A project with an `infra/Pulumi.yaml` is the agent template's Pulumi project and is deployed as a custom application with Pulumi, even when it could fit in one container. Anything that doesn't fit in one container is deployed the same way. Pulumi deploys the agent, MCP server and web app separately.

On this path the agent, its tools, its API and its UI run in one process on one port, and `dr workload up` builds and deploys it.

The user may not be technical. Do the technical steps yourself and explain what's happening in plain words. Don't ask them for ids, YAML or commands when you can find or run them yourself.

Start from an implemented agent: a single Python project with no `infra/Pulumi.yaml`. `<target_dir>` is the directory that holds the agent code and, when there is one, `agent_spec.md`. Without a spec, work from the code.

## 1. Choose the deploy path

If agent assist hasn't already picked this path, read and follow [references/deploy-path.md](references/deploy-path.md). Continue here only if it picks the Workload API.

## 2. Check the CLI

1. `dr --version`. If missing, run `curl https://cli.datarobot.com/install | sh`.
2. `dr self update --force`. Always run it. Don't try to judge whether the installed version is new enough.
3. `dr auth check`. If it fails, run `dr auth login`. It opens a browser. Tell the user: "A DataRobot sign-in page just opened. Sign in there and come back."
4. `dr workload up --help`. If it says unknown command, the update didn't take. Don't ask the user to fix it. In section 3, still check the app and store the tool secrets, but skip `dr workload config`, which is missing too. Then deploy with `references/deploy-fallback.md` instead of section 4.

## 3. Configure the deploy (once)

First read and follow `references/app-contract.md`. It checks that the code in `<target_dir>` meets what the deploy needs and fixes what doesn't. Don't configure until it passes.

`dr workload config` writes `.datarobot.yaml`, the deploy definition. It lives in the repo with the code. There's no terminal here, so every answer is a flag. The shell's working directory often isn't `<target_dir>`, so pass `--dir <target_dir>` to every `dr workload` command in this skill:

```bash
dr workload config --yes --skip-env --dir <target_dir> \
  --name <agent-name> --type agent \
  --build-mode generated \
  --execution-environment "[DataRobot] Python 3.12 Applications Base" \
  --entrypoint "uvicorn <entry point> --host 0.0.0.0 --port 8080" \
  --port 8080 --health /healthz
```

`--skip-env` keeps the local `.env` out of the manifest. Without it, `config` uploads the user's own `DATAROBOT_API_TOKEN` from that file as a stored credential. The block below gives the deployed agent a key from the platform instead. `--type` can't be changed later. If the execution environment isn't found, look one up yourself: `GET /executionEnvironments/?searchFor=Python&limit=10`. If that returns 403, the user needs their admin. Give them a message to send: "Which Python 3.12 execution environment should I use to deploy an agent with the Workload API?" If config says a manifest already exists, don't delete it. Edit `.datarobot.yaml` instead.

Add the environment to the primary container (`artifact`, `spec`, `containerGroups`, `containers`) in `.datarobot.yaml`:

```yaml
environmentVars:
  - name: DATAROBOT_ENDPOINT
    value: <endpoint>   # eval "$(dr auth export)"; echo "$DATAROBOT_ENDPOINT"
  - name: DATAROBOT_API_TOKEN
    source: api-key                           # a key with the user's permissions, tied to this workload
  - name: SOME_TOOL_API_KEY
    source: dr-credential
    drCredentialId: <credential id>
    key: apiToken
```

Store each tool secret as a DataRobot credential yourself once the user has put it in `.env`. Follow `references/tool-secrets.md`. Don't ask the user to create credentials or find ids. Don't use `--sync-env` for this: it uploads every variable in `.env`, including `DATAROBOT_API_TOKEN`.

## 4. Deploy

```bash
dr workload up --yes --output-format json --dir <target_dir>
```

Tell the user it takes a couple of minutes. The first run creates the artifact, uploads the code, builds the image and starts the workload. Don't pass `--detach`; wait for it. The JSON has `workloadId`, `endpoint` and `status`.

`up` writes the workload id into `.datarobot.yaml`. That file is how the next deploy finds the same agent. If `<target_dir>` is a git repo, commit it yourself. Tell the user not to delete it.

Redeploy with the same command. It only applies what changed. Env var, port or probe changes don't rebuild. Code and dependency changes do. Either way the new version rolls out, and a rollout can take several minutes, an env-only change included. Tell the user it may take a while, wait for `up` to return, and don't start a second deploy because it feels slow. Use `--force-build` only when a rebuild is needed and nothing changed, for example the image is gone from the registry.

`up` only manages fields that `.datarobot.yaml` names, and it puts those back if someone changed them in the UI. Make changes in the file, not the UI. If the user says they changed a setting in DataRobot, run `dr workload up --dry-run --diff --dir <target_dir>` first. It prints every field the deploy would change and changes nothing. Tell the user in plain words what would be changed back.

If the workload is locked (see 6), ask before every `up`: "This will update the agent people are using now. Go ahead?"

If `up` or `config` fails, handle it yourself without asking the user:

- `unknown command`: the update didn't take. Go straight to the fallback below.
- 403 `Workload API is disabled in feature flags`, from any call: the Workload API is off for the account. Don't retry and don't use the fallback, which calls the same API. Switch to Pulumi as in [references/deploy-path.md](references/deploy-path.md) and tell the user why.
- `.datarobot.yaml references credentials that cannot be used`: the credential id is wrong, or the credential was stored in another DataRobot environment. Store the secret again as in `references/tool-secrets.md` and fix `drCredentialId`. Ignore the CLI's hint to run `--sync-env`.
- A build log with `Distribution not found at: file:///...`: the project depends on a package outside `<target_dir>`. Switch to Pulumi as in [references/deploy-path.md](references/deploy-path.md) and tell the user why.
- Anything else that isn't about the app: read and follow `references/deploy-fallback.md`. Keep the app as it is. Only the deploy steps change.

## 5. Check it answers

`up` succeeding means the container is healthy, not that the agent works. `/healthz` never calls the LLM. Check two things:

```bash
eval "$(dr auth export)"   # never print the token
curl -sS -w "\n%{http_code}\n" "<endpoint>healthz"   # no token: expect 401
```

`<endpoint>` ends with a slash, so append paths without one. A `503` with `No LRS is registered for this path` seconds after `up` reports the workload running means the route isn't live yet. Retry after 10 seconds and don't redeploy.

A 200 means anyone with the link can use the agent, because the app has no sign-in of its own. Don't share the link. Tell the user: "Your agent is reachable without signing in to DataRobot. Please check with your DataRobot admin before sharing it."

Then send one example from the spec's `examples` to the chat API with `-H "Authorization: Bearer $DATAROBOT_API_TOKEN"`. With no spec, send a simple request that the code's API accepts. If it fails, check `dr workload logs --level error --dir <target_dir>`. It's usually the env block from section 3. Then give the user the link and tell them to open it in a browser where they're signed in to DataRobot.

If something breaks later:

- Assets or API calls 404: a URL is missing the prefix.
- 401 and the request isn't in the logs: the frontend sent `Authorization`, or the browser has no DataRobot session.
- Empty logs don't mean healthy. Some clusters don't collect them. Use `dr workload status --dir <target_dir>`, then the `datarobot-workload-api` skill, section 2.

## 6. Before you hand it over

Ask the user about these in plain words and let them decide.

- Keeping it on. Say: "Right now your agent turns off 8 hours after it starts, even if people are using it. Want me to make it permanent? Once I do, every future update replaces it without downtime. This can't be undone." If yes, run `dr workload promote --yes --dir <target_dir>`. It locks the running draft in place without a restart. `dr workload up --yes --promote --dir <target_dir>` does the same at the end of a deploy.
- Sharing. Ask who should have access, by DataRobot username or email. Then do it yourself: `GET /workloads/{id}/sharedRoles`, add the new people, and `PATCH /workloads/{id}/sharedRoles` with the full list. The PATCH replaces the whole list, so keep the owner in it or they lose access. The body is `{"operation": "updateRoles", "roles": [{"shareRecipientType": "user", "username": "<owner username>", "role": "OWNER"}, {"shareRecipientType": "user", "username": "<username>", "role": "CONSUMER"}]}`, with one entry per person. Copy the existing entries from the GET response, owner first. A 204 means it worked. Roles are uppercase: `OWNER`, `USER`, `CONSUMER`. Use `CONSUMER` for people who only use the agent. If the body is rejected, the 422 names the expected shape. Tell the user that the people they added need to be signed in to DataRobot to open the link, and that the agent acts with the user's own DataRobot permissions when it calls DataRobot.
- Removing it. Only say: "If you want it gone later, just tell me." Don't delete anything now. When the user later asks to remove it, confirm once, then run `dr workload delete --purge --yes --dir <target_dir>`. It removes the workload, its draft artifact and the local deploy state. A locked artifact, draft artifacts from earlier code deploys, and the credentials you stored yourself stay, so say so. Remove old drafts with `dr artifact delete <artifact id>` if the user wants a clean account.
