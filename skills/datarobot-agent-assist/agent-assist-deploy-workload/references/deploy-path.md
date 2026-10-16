# Choose the deploy path

Agent assist can deploy an agent two ways:

- **Workload API.** For a project with no `infra/Pulumi.yaml`. The agent, its tools, its API and its UI run in one container, and `dr workload up` builds and deploys it. Follow [../SKILL.md](../SKILL.md).
- **Custom application with Pulumi.** The agent template's own deploy. The agent, MCP server and web app are deployed separately. Follow [pre-deployment-checklist.md](../../agent-assist-build/references/pre-deployment-checklist.md).

The Workload API is for single Python projects that don't use a Pulumi template. Read `agent_spec.md` (when there is one) and the code in `<target_dir>` and make the call yourself. Don't ask the user to choose between architectures, and don't ask them the questions below. Run the checks yourself.

## First, check for a Pulumi template

If `<target_dir>/infra/Pulumi.yaml` exists, use Pulumi and stop here. The project is the agent template or another Pulumi project, even when it would fit in one container. If it's already deployed with Pulumi, keep it there, or the user ends up with two copies. Switch only if the user asks, and tell them the old deployment keeps running until they remove it.

## Then, check the Workload API is on for this account

The Workload API is switched on per account or organization. Check it before the other checks. The check needs the CLI installed and signed in. If `dr` is missing or `dr auth check` fails, do steps 1 to 3 of section 2 in [../SKILL.md](../SKILL.md) first.

```bash
eval "$(dr auth export)"   # never print the token
curl -sS -H "Authorization: Bearer $DATAROBOT_API_TOKEN" "$DATAROBOT_ENDPOINT/workloads/?limit=1"
```

A 403 that says `Workload API is disabled in feature flags` means it's off. That's an account setting, not something the fallback can fix. Use Pulumi and tell the user: "The Workload API isn't turned on for your DataRobot account, so I'll use the standard deployment path. If you want the faster path, ask your DataRobot admin to enable the Workload API for your organization." A 200 means it's on.

## Use Pulumi if any of these are true

- The code doesn't fit in one container, or a Workload deploy already failed for that reason: a dependency outside `<target_dir>` (a `file://` path, a symlink, or `Distribution not found at: file:///...` in the build log), or an app that needs more than one process or port. Don't try the Workload API again for this project.
- A tool needs a GPU, a lot of memory, or moves a lot of data (tens of GB). That tool should be its own deployment so it can scale on its own.
- Some tools call complicated third-party systems that the user wants to deploy, debug and version separately from the agent.
- The tools have to be published as a standalone MCP server that other agents or teams use on their own schedule. One agent serving chat, A2A, MCP and a web UI from the same process still fits in a single container.
- The user needs features that today only come with a custom model deployment: guard models, moderation, custom metrics, registry approvals.
- The agent has more than about 10 tools, or several interfaces owned by different people.
- The spec uses `llm_deployment_id`. The Workload API path hasn't been tried with it.

## Otherwise use the Workload API

This is the default. Most agents fit. It's easier to debug, deploys in a couple of minutes, and can still be scaled up with more CPU, memory or replicas. If the code later turns out not to fit in one container ([app-contract.md](app-contract.md)), come back here and use Pulumi.

## Unclear or overridden

If a condition is really unclear, ask one plain question about what the agent needs, for example: "Will other teams need to use these tools on their own, without your agent?"

If the user asks for a path ("deploy with the Workload API", "simple agent assist", "use Pulumi", "the standard way") or disagrees with the call, go with the user.

## Tell the user and hand off

Tell them in one plain sentence, for example: "Your agent is simple enough to run as one app, so I'll deploy it with the Workload API," or "Your agent needs the bigger setup, so I'll use the standard deployment path."

- Workload API: continue with section 2 of [../SKILL.md](../SKILL.md).
- Pulumi: read and follow [pre-deployment-checklist.md](../../agent-assist-build/references/pre-deployment-checklist.md) end to end. If the project wasn't built from the template, that checklist offers option 2 first.
