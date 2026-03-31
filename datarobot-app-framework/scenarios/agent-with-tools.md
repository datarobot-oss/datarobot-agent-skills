---
name: agent-with-tools
intent: [agent with custom tools, agent with DataRobot tools, agent calling predictions, agent with DR integration, custom tool, global tool]
tier: 3
components:
  - af-component-base
  - af-component-llm
  - af-component-agent
  - af-component-tool          # single-purpose custom tool
  - af-component-global-tool   # optional: shared tool across multiple agents
output: Agent with custom tool(s) + DataRobot deployment
---

> **Note:** This scenario builds on minimal-agent (Tier 1). Complete Steps 1–5 of
> [minimal-agent.md](minimal-agent.md) first, then continue here.

## Step 6 — Add a custom tool

```bash
dr component add tool
```

> TODO: confirm exact CLI command and prompts for af-component-tool.

## Step 7 — Add a global tool (optional)

Use when the tool should be reusable across multiple agents in the same recipe.

```bash
dr component add global-tool
```

> TODO: confirm exact CLI command and prompts for af-component-global-tool.

## DataRobot-native tool patterns

Common patterns for tools that integrate with DataRobot:

- **Call a DR deployment for predictions**: use `af-component-prediction` pattern
- **Interact with DR deployments**: use `af-component-deployment` pattern

> TODO: document the add commands and wiring for prediction/deployment tools once confirmed with the team.

## Test locally

```bash
cd agent
uv run python cli.py execute --user_prompt "Your test prompt that exercises the tool"
cat execute_output.json | jq -r '.choices[0].message.content'
```

## Deploy

```bash
dr task deploy
```
