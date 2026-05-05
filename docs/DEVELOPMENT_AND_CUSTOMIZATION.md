# Development and customization

Use this guide to create or customize a DataRobot skill, validate your changes, and understand how skills execute DataRobot workflows.

## Before you start

To use DataRobot skills, you need:

- **A DataRobot account** with API access
- **A DataRobot API token** and endpoint
- **A Python environment** where your coding agent can install packages

The agent installs the `datarobot` Python package automatically when needed.

## Create or customize a skill

The easiest way to create a new skill is to start from an existing one that is close to your use case.

1. Copy one of the existing skill folders, such as `skills/datarobot-model-training/`, and rename it.
2. Update the new folder's `SKILL.md` frontmatter and instructions:

   ```yaml
   ---
   name: datarobot-my-skill-name
   description: Describe what the skill does and when to use it
   ---

   # Skill title
   Guidance + examples + guardrails
   ```

3. Follow the naming convention `datarobot-<category>` for both the folder name and the `name` field in `SKILL.md`.
4. Add or update any supporting scripts, templates, or documents referenced by the skill.
5. Reinstall or reload the skill bundle in your coding agent so the updated skill is available.
6. Test the skill with a prompt that exercises the workflow you expect users to follow.

## Validate your changes

This repository includes validation and linting tools to help maintain consistency and quality across all skills.

### Local prerequisites

Install these tools before running validation tasks:

- [Task](https://taskfile.dev/) - Task runner (install with `brew install go-task` or `sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d`)
- [uv](https://docs.astral.sh/uv/) - Python package and environment manager (install with `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Common tasks

Run `task --list` to see the full task list. The most useful commands during development are:

```bash
# Validate all skills (naming convention, structure, frontmatter)
task validate

# Lint all Python scripts with ruff
task ruff:check

# Format all Python scripts with ruff
task format

# Run all checks (validate + lint + format check)
task lint

# Default task (runs lint)
task
```

If you want a single command before opening a pull request, run `task lint`.

### Validation rules

The `bin/validate_skills.py` script enforces the following rules:

1. **Naming convention:** All skill folders must start with `datarobot-`.
2. **Structure:** Each skill must include a `SKILL.md` file.
3. **Frontmatter:** The `name` field in `SKILL.md` must match the folder name.

Example:

```text
datarobot-my-skill/
  └── SKILL.md
      ---
      name: datarobot-my-skill  # Must match folder name
      description: ...
      ---
```

### Continuous integration

This repository uses GitHub Actions for automated checks:

- **[Validate Skills](../.github/workflows/validate-skills.yml)** - Validates skill naming and structure on every push and pull request
- **[Trivy Security Scan](../.github/workflows/trivy-scan.yml)** - Scans for secrets and security issues daily and on every push and pull request

All checks must pass before merging a pull request.

## How skills work with DataRobot

By default, DataRobot skills guide your coding agent to use the **DataRobot Python SDK** directly. A typical flow looks like this:

1. The agent installs the `datarobot` package if it is not already available.
2. The agent reads the relevant skill instructions and examples.
3. The agent writes and runs Python code to interact with DataRobot.

For example, if you ask for a prediction dataset template, the agent reads `skills/datarobot-predictions/SKILL.md`, then writes Python code with the `datarobot` SDK to retrieve deployment features and generate the template.

### Optional: MCP server support

If you have a DataRobot MCP server running, agents can also use MCP tools instead of calling the SDK directly. See the [MCP Server Template](https://github.com/datarobot-community/datarobot-mcp-template) for more information, and use the `datarobot-mcp-server-deployment` skill (`skills/datarobot-mcp-server-deployment/SKILL.md`) for deploy steps, client wiring, and an environment gaps checklist.
