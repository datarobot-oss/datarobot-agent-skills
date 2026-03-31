# Development and customization

This guide covers how to create or customize a DataRobot skill, validate changes, and understand how skills work with DataRobot.

## Contribute or customize a skill

1. Copy one of the existing skill folders (for example, `skills/datarobot-model-training/`) and rename it.
2. Update the new folder's `SKILL.md` frontmatter:

   ```yaml
   ---
   name: datarobot-my-skill-name
   description: Describe what the skill does and when to use it
   ---

   # Skill Title
   Guidance + examples + guardrails
   ```

3. **Important:** Follow the naming convention `datarobot-<category>` for all skill names and folder names.
4. Add or edit supporting scripts, templates, and documents referenced by your instructions.
5. Reinstall or reload the skill bundle in your coding agent so the updated folder is available.

## Development and validation

This repository includes automated validation and linting tools to help maintain consistency and quality across all skills.

### Prerequisites

- [Task](https://taskfile.dev/) - Task runner (install: `brew install go-task` or `sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d`)
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Available tasks

Run `task --list` to see the available tasks:

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

- **[Validate Skills](../.github/workflows/validate-skills.yml)** - Validates skill naming and structure on every push and pull request.
- **[Trivy Security Scan](../.github/workflows/trivy-scan.yml)** - Scans for secrets and security issues daily and on every push and pull request.

All checks must pass before merging pull requests.

## How skills work with DataRobot

Skills guide your coding agent to use the **DataRobot Python SDK** directly. The agent will:

1. Install the `datarobot` Python package if needed.
2. Use the SDK based on skill instructions and examples.
3. Write and execute Python code to interact with DataRobot.

For example, when you ask, "Generate a prediction dataset template," the agent reads `skills/datarobot-predictions/SKILL.md`, then writes Python code with the `datarobot` SDK to retrieve deployment features and generate the template.

### Optional: MCP server support

If you have a DataRobot MCP server running, agents can also use MCP tools instead of calling the SDK directly. See the [MCP Server Template](https://github.com/datarobot-community/datarobot-mcp-template) for more information.

## Runtime prerequisites

To use DataRobot skills, you need:

- **A DataRobot account** with API access
- **A DataRobot API token** and endpoint
- **A Python environment** where your coding agent can install packages

The agent will automatically install the `datarobot` Python package when needed.
