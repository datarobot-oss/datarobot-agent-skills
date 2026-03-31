---
name: agent-with-ui
intent: [agent with chat UI, agent with frontend, agent with React, agent with web UI, chat interface, custom frontend]
tier: 2
components:
  - af-component-base
  - af-component-llm
  - af-component-agent
  - af-component-fastapi-backend-chat
  - af-component-react
plugins:
  - af-component-fastapi-backend-oauth        # optional: add auth
  - af-component-fastapi-backend-persistence-sqlite  # optional: add chat history
output: React chat UI + FastAPI backend + DataRobot deployment
---

> **Note:** This scenario builds on minimal-agent (Tier 1). Complete Steps 1–5 of
> [minimal-agent.md](minimal-agent.md) first, then continue here.

## Step 6 — Add chat backend

```bash
uvx copier copy https://github.com/datarobot/af-component-fastapi-backend-chat .
```

## Step 7 — Add React frontend

```bash
uvx copier copy https://github.com/datarobot/af-component-react .
```

## Optional plugins

**Add auth (OAuth):**
```bash
uvx copier copy https://github.com/datarobot/af-component-fastapi-backend-oauth .
```

**Add chat history / persistence:**
```bash
uvx copier copy https://github.com/datarobot/af-component-fastapi-backend-persistence-sqlite .
```

## Wiring: FastAPI ↔ Agent

> TODO: document the integration point between af-component-fastapi-backend-chat and af-component-agent.
> Key files and wiring pattern to be filled in once confirmed with the team.

## Test locally

```bash
dr run dev
```

Visit `http://localhost:8080` for the React UI.

## Deploy

```bash
dr task deploy
```
