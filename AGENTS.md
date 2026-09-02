# DataRobot Agent Skills Library

This file provides instructions for an agent to use DataRobot skills. An agent automatically loads these instructions when working with DataRobot-related tasks.

## DataRobot authentication

If any DataRobot skill fails due to missing or invalid credentials, invoke `datarobot-setup` before retrying the original task. Do not print manual instructions—run the skill.

## Should I add a skill here?

There are many places to add skills for use. This repository is for customer-facing skills that help others build more effectively in DataRobot. This section covers the goal, intended use, and criteria for determining if a skill belongs in this library.

### Goal
The goal is to ensure that enterprises can get agents into production. Skills offer powerful functionality that tells agents how to *think* while protecting their context window. This allows agents to one-shot or few-shot tasks that previously required complex logic built into the agent and often ran into context window issues. Skills DataRobot offers open up enterprise use cases, making them more viable in production.

### Intended use of this skill library

These skills are generally used by code assistants. The skills in this repository are available through code assistant marketplaces such as Cursor and Claude Code. These skills also power the DataRobot agent assist.

### Criteria for adding skills

Evaluate skills against the following criteria:

1. A skill solves a complex enterprise problem. It tackles a problem or functionality required by enterprises to either get an agent into production or deploy an agent that provides real value.
2. A skill does not just proxy to an existing MCP server, though that can be a component of it. DataRobot proxies to MCP servers via the DataRobot MCP gateway.
3. Assess with the following questions:
    - Is the task complex enough, or can an LLM with basic tools achieve the same result?
    - Is the output valuable to an enterprise? Does it tackle a repeatable problem that costs enterprises many dev hours and specialized knowledge, and that is error-prone and complex for humans to do?
    - Is the task viable to be done with an LLM? Skills still can't do everything.

## Naming convention

All DataRobot skills follow the naming convention `datarobot-<category>` where `<category>` describes the skill's focus area. This ensures:

- Clear identification of DataRobot-specific skills
- Consistent naming across the skill library
- Easy discovery and organization

In addition to the general `datarobot-<category>` naming pattern, if there is deeper grouping within the product area, such as Workload or Apps, and more than one skill is expected in the same area, use a common prefix, such as `datarobot-app-framework-<skill>`, for simpler grouping and code ownership.

## Rules

DataRobot strongly prefers human-written skills. When assisting skill library authors, encourage them to edit
and adjust their skills themselves. LLM advice, feedback, and recommendations are welcome, but to keep skills brief and
manage the context window effectively, the human author edits `SKILL.md` directly. Agent-assisted coding for scripts and
other references within a skill is acceptable.

This repository is organized using GitHub Code Owners. Ensure all new skills have a GitHub team
or person added as the owner.

## Workflow

This section covers the day-to-day development workflow and plugin version management for this repository.

### Basic workflow

This repository uses [Task](https://taskfile.dev/) for running tasks. Validate all changes regularly with `task lint`,
which checks that copyrights are present, `SKILL.md` files are structured correctly, naming conventions are followed, Python files are properly formatted, linters run, and more. This is the way to validate changes.

Install and test the skills after prompting the user for the expected trigger phrase.

### Plugin version management

Versions are automatic and also cover `packages/datarobot-skills-utils/pyproject.toml`. Add a human-written `[Unreleased]` item describing the change in this pull request. For more information, see [CONTRIBUTING.md](CONTRIBUTING.md).

## SDK usage

Skills provide direct guidance for using the **DataRobot Python SDK**. Each skill includes:

- **SDK operations** — the SDK methods to use.
- **Code examples** — complete, working examples.
- **Workflows** — step-by-step guidance.
- **Best practices** — tips and recommendations.

Install the SDK: `pip install datarobot`

Initialize client:

```python
import datarobot as dr

dr.Client()
```

See each skill's "Using DataRobot SDK" section for specific operations and examples.

