---
name: datarobot-agent-assist
description: >-
  Use when the user wants to design, build, code, simulate, or deploy an AI agent (not a predictive
  model) to DataRobot; mentions agent_spec.md, dr-assist, datarobot-agent-assist, dress rehearsal,
  swarm simulation, or the DataRobot agent template; wants to scaffold a LangGraph, CrewAI,
  LlamaIndex, NAT, or Base agent targeting DataRobot; wants to add an MCP server, backend API, or
  React frontend to a DataRobot agent application; or uses the DataRobot CLI (dr) to build or
  deploy an agentic custom application. Covers the full workflow: agent design, agent_spec.md
  authoring, dress-rehearsal simulation, adversarial swarm simulation, and deployment.
---

# DataRobot Agent Assist

## On Activation

First, check whether the user's message already implies a clear intent:

**If intent is clear** — route directly without showing the menu. Clear intents:
- Design / build / create an agent → read `agent-assist-main/SKILL.md`, jump to Clarification Phase
- Code / implement an agent → read `agent-assist-main/SKILL.md`, jump to 2. Coding an AI Agent
- Battle-test / simulate / swarm / harden / test my agent → read `agent-assist-simulate/SKILL.md`, jump to Pre-flight Check
- Deploy an agent → read `agent-assist-main/SKILL.md`, jump to 3. Deploying an AI Agent

**If intent is unclear** (e.g. bare `/datarobot-agent-assist` with no context, or a vague message like "help" or "get started") — present this menu before reading any sub-skill file:

```
Welcome! I help you design, build, and deploy AI agents on DataRobot.

What would you like to do?
  1. Design an agent        — describe your idea and build agent_spec.md
  2. Code the agent         — implement an existing agent_spec.md
  3. Battle-test the agent  — adversarial and edge case testing before deploying
  4. Deploy                 — deploy your agent to DataRobot
```

Once the user selects an option, route using the same table above.

In both cases — **skip the sub-skill's own On Activation menu**. The user has already expressed or selected their intent.

---

## Workflows

### `agent-assist-main` — Design, code, and deploy

Read `agent-assist-main/SKILL.md` for options 1, 2, and 4.

### `agent-assist-simulate` — Battle-test an existing agent

Read `agent-assist-simulate/SKILL.md` for option 3. Also use directly when the user says
"simulate my agent", "run swarm", "adversarial testing", "harden my agent", or "test my spec" —
in these cases skip the menu above and go straight to the Pre-flight Check.

---

## Important

Do not assume sub-skill instructions are automatically loaded by the harness. Always read the
relevant sub-skill SKILL.md before proceeding with that workflow.
