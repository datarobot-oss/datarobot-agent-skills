---
name: minimal-agent
intent: [build agent, deploy agent, CrewAI, LangGraph, LlamaIndex, agent API, agent playground, no UI, agentic workflow]
tier: 1
components:
  - af-component-base
  - af-component-llm
  - af-component-agent
output: API endpoint + DataRobot agent playground UI
---

## Step 1 — Create recipe directory

```bash
mkdir recipe-my-agent && cd recipe-my-agent
```

> Convention: always prefix with `recipe-`. For team projects, create the repo in the DataRobot GitHub org first and clone it.

## Step 2 — Scaffold base

```bash
uvx copier copy https://github.com/datarobot/af-component-base .
```

Answer the interactive questions about your recipe name and settings. Defaults are safe.

## Step 3 — Add LLM

```bash
uvx copier copy https://github.com/datarobot-community/af-component-llm .
```

Key prompts:
- **LLM folder name**: `llm` (default)
- **Model name**: `azure-openai-gpt-4o-mini` or as required
- **Base answers file**: `.datarobot/answers/base.yml`

Creates `infra/infra/llm.py` and gateway config files.

## Step 4 — Add agent

```bash
dr component add agent
```

Key prompts:
- **Agent folder name**: `agent` (default)
- **Low-code YAML (NeMo Toolkit)?**: No (unless user specifically requests it)
- **Framework**: CrewAI / LangGraph / LlamaIndex — choose based on user need
- **Base answers file**: `.datarobot/answers/base.yml`
- **LLM answers file**: `.datarobot/answers/llm-llm.yml`
- **MCP answers file**: `.datarobot/answers/drmcp-mcp_server.yml` (optional — skip if not using MCP tools)

Creates:
```
agent/
├── agent/myagent.py   ← multi-agent workflow (customize here)
├── cli.py             ← local testing tool
├── dev.py             ← local dev server
└── tests/
infra/infra/agent.py   ← Pulumi deployment config
```

## Step 5 — Configure environment

```bash
dr dotenv setup
```

Key prompts:
- **Agent port**: 8842 (default)
- **DataRobot execution environment**: select from available environments
- **Execution environment version ID**: ID of the environment version to use
- **Pulumi passphrase**: any value (used for state encryption)
- **Use case**: can leave blank
- **LLM Gateway config**: select LLM Gateway with External Model

Press enter to accept defaults for most prompts.

## Step 6 — Test locally

```bash
cd agent
uv run python cli.py execute --user_prompt "Write a blog post about AI in healthcare"
cat execute_output.json | jq -r '.choices[0].message.content'
```

For iterative development with auto-reload:

```bash
dr run dev                                                              # Terminal 1
cd agent && uv run python cli.py execute --user_prompt "Test prompt"   # Terminal 2
```

Server runs at `http://localhost:8842` and reloads on code changes.

## Step 7 — Deploy

```bash
dr task deploy
```

Prompts to create a stack (name it anything), previews LLM + Agent resources, then deploys both. Outputs deployment IDs and URLs.

Check deployment info anytime:

```bash
dr task infra:info
```

## What you get

- Default: Planner agent (research + outline) + Writer agent (content creation)
- Sequential workflow with MCP tools support
- Agent playground UI in DataRobot
- API endpoint for integration

## Deploy updates

```bash
dr run deploy
```

## Tear down

```bash
dr task infra:down
```

## Customize

Edit `agent/agent/myagent.py` to:
- Change agent roles, goals, or task descriptions
- Add more agents to the crew
- Integrate additional MCP tools
- Switch framework (CrewAI → LangGraph → LlamaIndex)
