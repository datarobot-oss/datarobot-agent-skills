---
name: datarobot-agent-assist
description: >-
  Use when the user wants to design, build, code, simulate, or deploy an AI agent (not a predictive
  model) to DataRobot; mentions agent_spec.md, dr-assist, datarobot-agent-assist, dress rehearsal,
  or the DataRobot agent template; wants to scaffold a LangGraph, CrewAI, LlamaIndex, NAT, or Base
  agent targeting DataRobot; wants to add an MCP server, backend API, or React frontend to a
  DataRobot agent application; or uses the DataRobot CLI (dr) to build or deploy an agentic custom
  application. Covers the full workflow: agent design, agent_spec.md authoring, dress-rehearsal
  simulation via the DataRobot LLM Gateway, template-based coding, and deployment.
---

# DataRobot Agent Assist

This skill covers building and deploying AI agents on DataRobot.

## Sub-skills

- **[agent-assist-build](agent-assist-build/SKILL.md)** — Design, code, and deploy an AI agent on DataRobot. Covers `agent_spec.md` authoring, dress-rehearsal simulation, template-based coding, and deployment.
- **[agent-assist-simulate](agent-assist-simulate/SKILL.md)** — Adversarially test and harden a deployed agent using swarm simulation, attack testing, convergence loops, and automated evaluation reporting.

Load the relevant sub-skill based on the user's intent.
