# DataRobot App Framework: Agent

Build and deploy agents (CrewAI, LangGraph, LlamaIndex) to DataRobot in minutes.

## Prerequisites

```bash
pip install datarobot-cli
curl -LsSf https://astral.sh/uv/install.sh | sh
dr auth set-url && dr auth login
```

## Quick Start

```bash
# 1. Create recipe
mkdir recipe-my-agent && cd recipe-my-agent
uvx copier copy https://github.com/datarobot/af-component-base .

# 2. Add LLM
uvx copier copy https://github.com/datarobot-community/af-component-llm .

# 3. Add agent (choose framework: CrewAI, LangGraph, LlamaIndex)
dr component add agent

# 4. Configure
dr dotenv setup

# 5. Test locally
cd agent
uv run python cli.py execute --user_prompt "Write about AI"
cat execute_output.json | jq -r '.choices[0].message.content'

# 6. Deploy
dr task deploy
```

**What you get:**
- Default: Planner agent (research) + Writer agent (content creation)
- Sequential workflow with MCP tools support
- Agent playground UI in DataRobot
- API endpoint for integration

**Key files:**
- `agent/agent/myagent.py` - Agent workflow (customize here)
- `agent/cli.py` - Testing tool
- `infra/infra/agent.py` - Deployment config

## Common Tasks

**Customize agents** - Edit `agent/agent/myagent.py` to change roles, goals, tasks, or add more agents.

**Dev with auto-reload:**
```bash
dr run dev  # Terminal 1
cd agent && uv run python cli.py execute --user_prompt "Test"  # Terminal 2
```

**Deploy updates:**
```bash
dr task deploy
```

**Clean up:**
```bash
dr task infra:down
```

## Resources

**Documentation:**
- App Framework Docs: [Confluence Space](https://confluence.corp.datarobot.com/display/AF)
- DataRobot CLI: https://docs.datarobot.com/en/docs/more-info/app-framework/cli.html
- Agent Templates: https://github.com/datarobot-community/datarobot-agent-templates

**Component Repos:**
- Base: https://github.com/datarobot/af-component-base
- LLM: https://github.com/datarobot-community/af-component-llm
- Agent: https://github.com/datarobot-community/af-component-agent
- Discover more: Search `af-component` in datarobot/datarobot-community orgs

**Community:**
- Slack: #applications
- Diffington (auto-updates): Request in #applications