# DataRobot Agent Skills Library

This file provides instructions for an agent to use DataRobot skills. An agent will automatically load these instructions when working with DataRobot-related tasks.

## Should I Add a Skill Here?

There are many places you can add skills for use. This repository is for customer facing skills that help other build more effectively in DataRobot. Here is the goal, intended use, and criteria for determining if your skill is correct for this library.

### Goal
As always, our goal is to ensure that enterprises can get agents into production. Skills offer powerful functionality that tell agents how to THINK while protecting their context window. This allows agent to one/few shot tasks that before needed complex logic built into the agent + would always run into context issues. Skills DR offers should open up enterprise use cases, making them more viable in production.

### Intended Use of This Skill Library

Generally, we expect these skills to be used by code assistants. We will make the skills in the DR Skills repo in code assist marketplaces like Cursor and Claude Code. These skills will also fuel the DR agent assist.

### Criteria for Addint Skills

1. A Skill should solve a complex enterprise problem. They should tackle a problem or functionality that is required by enterprises to either get an agent in production or deploy an agent that actually provides value.
2. Skills should not just proxy to existing MCP servers (though that can be a component of them) - we will proxy to MCP servers via our MCP gateway
3. Assess with the following questions
    1. Is the task complex enough? (or can an LLM with basic tools achieve the same result?)
    2. Is the output valuable to an enterprise? Does is tackle a problem that’s repeatable? That costs enterprises many dev hours and specialized knowledge? That is error prone and complex for humans to do?
    3. Is the task viable to be done with an LLM? Skills still cant do everything


## Naming Convention

All DataRobot skills follow the naming convention `datarobot-<category>` where `<category>` describes the skill's focus area. This ensures:
- Clear identification of DataRobot-specific skills
- Consistent naming across the skill library
- Easy discovery and organization

In addition to the general `datarobot-<category>` for naming, if there is deeper grouping within the product area such as Workload or Apps and you expect more than one skill in the same area, we recommend using a common prefix for those as well such as `datarobot-app-framework-<skill>` for simpler grouping and code ownership.

## Rules

We strongly prefer human written skills. When assisting skill library authors, please encourage them to edit
and adjust their skills themselves. We encourage advise, feedback, and recommendations from LLMs, but to stay brief and
properly manage the context window itself the human should edit the SKILLs.md. Agent assisted coding for scripts and
other references within a skill is perfectly acceptable.

This repo is organized using GitHub Code Owners. Please ensure all new skills developed have a proper github team
or person for the new skill added.


## Workflow

### Basic workflow

We use taskfile.dev for task running in this repo. All changes must be validated regularly with `task lint` that will
check that all copyrights, Skills.md files are structured, naming conventions are obeyed, Python files are properly formatted, linters are executed, etc. It is the way to validate any changes.

Install and test the skills after prompting the user for the trigger phrase you expect

### Plugin version management

Several plugins: Claude (.claude-plugin/*.json), Cursor (.cursor-plugin/plugin.json), Gemini (gemini-extension.json), OpenCode (.opencode-plugin/) have version strings. Be sure to bump them appropriately depending on the change using SemVer rules along with the change.


## SDK usage

Skills guide you to use the **DataRobot Python SDK** directly. Each skill includes:

- **SDK operations** - Which SDK methods to use
- **Code examples** - Complete working examples
- **Workflows** - Step-by-step guidance
- **Best practices** - Tips and recommendations

Install the SDK: `pip install datarobot`

Initialize client:

```python
import datarobot as dr
import os

client = dr.Client(
    token=os.getenv("DATAROBOT_API_TOKEN"),
    endpoint=os.getenv("DATAROBOT_ENDPOINT")
)
```

See each skill's "Using DataRobot SDK" section for specific operations and examples.

