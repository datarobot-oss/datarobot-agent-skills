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

For broad or ambiguous Agent Assist requests, present this menu before reading a sub-skill file:

```
Welcome! I help you design, build, and deploy AI agents on DataRobot.

What would you like to do?
  1. Design an agent        — describe your idea and build agent_spec.md
  2. Code the agent         — implement an existing agent_spec.md
  3. Battle-test the agent  — test an implemented agent before deploying
  4. Deploy                 — deploy your agent to DataRobot
```

Once the user selects an option, read the relevant sub-skill file and jump directly to the corresponding section — **skip the sub-skill's own On Activation menu**:

| Choice | Sub-skill file | Jump to |
|---|---|---|
| 1 — Design | `agent-assist-build/SKILL.md` | Clarification Phase |
| 2 — Code | `agent-assist-build/SKILL.md` | 2. Coding an AI Agent |
| 3 — Battle-test | `agent-assist-simulate/SKILL.md` | Pre-flight Check |
| 4 — Deploy | `agent-assist-build/SKILL.md` | 3. Deploying an AI Agent |

---

## Workflows

### `agent-assist-build` — Design, code, and deploy

Read `agent-assist-build/SKILL.md` for options 1, 2, and 4.

### `agent-assist-simulate` — Battle-test an implemented agent

Read `agent-assist-simulate/SKILL.md` for option 3. Also use directly when the user says
"simulate my agent", "run swarm", "adversarial testing", "harden my agent", or "test my agent".
Swarm simulation is post-coding only. If implementation code exists, skip the menu and go straight
to the Pre-flight Check. Otherwise, explain that the agent must be implemented first and route the
user to option 2.

---

## Important

Do not assume sub-skill instructions are automatically loaded by the harness. Always read the
relevant sub-skill SKILL.md before proceeding with that workflow.
