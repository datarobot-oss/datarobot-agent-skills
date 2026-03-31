---
name: fastapi-app
intent: [FastAPI app, custom web app, FastAPI backend, simple app, web UI, custom application, no agent]
tier: core
components:
  - af-component-base
  - af-component-fastapi-backend
plugins:
  - af-component-react   # optional: add React frontend
output: FastAPI app deployed to DataRobot Custom Applications
---

> **Note:** Complete prerequisites first — see SKILL.md.

## Step 1 — Create recipe directory

```bash
mkdir recipe-my-app && cd recipe-my-app
```

> Convention: always prefix with `recipe-`. For team projects, create the repo in the DataRobot GitHub org first and clone it.

## Step 2 — Scaffold base

```bash
uvx copier copy https://github.com/datarobot/af-component-base .
```

Answer the interactive questions about your recipe name and settings. Defaults are safe.

## Step 3 — Add FastAPI backend

```bash
uvx copier copy https://github.com/datarobot/af-component-fastapi-backend .
```

Accept defaults for all prompts.

Creates `<name>/` directory (default: `web`) with:
```
web/
├── templates/index.html   ← customize your UI here
└── ...
```

## Step 4 — Configure and compose

```bash
dr task compose
dr start
```

## Step 5 — Test locally

```bash
dr run dev
```

Visit `http://localhost:8080` to see your app.

- `http://localhost:8080/docs` — FastAPI autodocs (Swagger)
- `http://localhost:8080/redoc` — ReDoc

App auto-reloads on code changes.

## Step 6 — Deploy

```bash
dr run deploy
```

Outputs the deployment URL. Visit with cmd-click / ctrl-shift-click.

## Add React frontend (optional)

```bash
uvx copier copy https://github.com/datarobot/af-component-react .
```

## Tear down

```bash
dr run infra:down
```

## Redeploy / move to another DR instance

```bash
dr auth set-url   # point to new instance
dr run deploy
```
