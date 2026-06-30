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

This skill contains two workflows. Read this file first, then follow the instructions in the
relevant sub-skill file based on what the user wants to do.

## Workflows

### 1. `agent-assist-main` — Build or modify an agent

Use when the user wants to:
- Design a new AI agent
- Create or update `agent_spec.md`
- Run dress rehearsal simulation (interactive, pre-coding)
- Write or modify agent code using the DataRobot template
- Deploy an agent to DataRobot

**→ Read and follow `agent-assist-main/SKILL.md`**

### 2. `agent-assist-simulate` — Test an existing agent

Use when the user wants to:
- Run adversarial swarm simulation against an existing `agent_spec.md`
- Automatically test for security breaches, behavioral edge cases, and restriction violations
- Harden the agent's system prompt through the convergence loop
- Get a simulation report (`eval_report.md`) before deploying

**→ Read and follow `agent-assist-simulate/SKILL.md`**

---

## Default workflow

When the user wants to build a new agent or has no `agent_spec.md` yet:

1. Follow `agent-assist-main` to design the agent and build `agent_spec.md`.
2. After the spec is complete, `agent-assist-main` will present next steps — swarm simulation is always one of them, before and after coding.
3. If the user chooses swarm simulation at any point, follow `agent-assist-simulate`.
4. After simulation, return to `agent-assist-main` for coding or deployment.

## Standalone simulation

If the user already has an `agent_spec.md` and only wants to test or harden it — skip `agent-assist-main` entirely and go directly to `agent-assist-simulate`. Trigger phrases: "simulate my agent", "run adversarial testing", "harden my agent", "test my spec".

---

## Important

Do not assume sub-skill instructions are automatically loaded by the harness. This file is the
routing and composition layer. Always read the relevant sub-skill SKILL.md before proceeding with
that workflow.
