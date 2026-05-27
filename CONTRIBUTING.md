# Contributing guidelines

Guidelines for developing and contributing to this project.

## List of project maintainers

- [Your Name](Your GitHub User URL)

## Opening new issues

- Before opening a new issue, check if there are any existing FAQ entries (if one exists), issues, or pull requests that match your case.
- Open an issue and label it accordingly — bug, improvement, feature request, etc.
- Be as specific and detailed as possible.

## Did you find a bug?

- Do not open a GitHub issue if the bug is a security vulnerability. Instead, email the maintainers directly or email oss-community-management@datarobot.com if they do not respond within seven days.
- Ensure the bug was not already reported in the project's Issues section.
- Open an issue as described above.

## Running e2e skill tests

Skill quality is evaluated end-to-end by an LLM judge. To keep CI cheap, unchanged skills are skipped via an MD5 cache at `tests/e2e/skill_hashes.json`.

### Local pre-commit hook (recommended)

Run once after cloning:

```
cp .env.example .env  # fill in DATAROBOT_ENDPOINT + DATAROBOT_API_TOKEN
task setup            # installs .githooks/ as the project hooks path
```

After that, any commit touching `skills/**` or `tests/e2e/**` will run the LLM judge on the affected skills, and — if they pass — stage the refreshed `skill_hashes.json` into the same commit. By the time the PR hits CI, the hashes already match and the e2e job is a no-op for those skills.

If `DATAROBOT_ENDPOINT` / `DATAROBOT_API_TOKEN` aren't set, the hook prints a notice and skips; CI will run the judge as a safety net. To bypass the hook for a single commit: `git commit --no-verify`.

### Running the suite manually

```
task test:e2e         # or: uv run --group e2e pytest tests/e2e/ -v
task test:e2e:force   # re-evaluate every skill, ignore the cache
```

CI does not write back to `main`; if the committed cache drifts the workflow logs a warning, and the fix is to run the command above locally and commit the refreshed file.

## Responding to issues and pull requests

This project's maintainers will make every effort to respond to any open issues as soon as possible.

If you don't get a response within seven days of creating your issue or pull request, send us an email at oss-community-management@datarobot.com.

## Should I add a skill here?

### Goal

The goal of this library is to ensure that enterprises can get agents into production. Skills offer powerful functionality that tells agents how to think while protecting their context window. This allows agents to one- or few-shot tasks that previously needed complex logic built into the agent, avoiding context window issues. Skills DataRobot offers should open up enterprise use cases, making them more viable in production.

### Intended use

These skills are intended for use by code assistants such as Cursor, Claude Code, VS Code Copilot, and similar tools. The skills in this library power the DataRobot agent assist and are distributed through code assistant marketplaces.

### Criteria

Before adding a skill, evaluate it against these criteria:

1. **Solves a complex enterprise problem**&mdash;the skill tackles a problem or functionality required by enterprises to either get an agent into production or deploy an agent that provides real value.
2. **Does not just proxy to an existing MCP server**&mdash;MCP server integration can be a component of a skill, but the skill itself must provide more than a thin wrapper.
3. **Passes the viability questions:**
   - Is the task complex enough, or can an LLM with basic tools achieve the same result?
   - Is the output valuable to an enterprise? Does it tackle a repeatable problem that costs enterprises many dev hours and requires specialized knowledge?
   - Is the task viable to be done with an LLM? Skills still can't do everything.

## Naming conventions

All DataRobot skills follow the naming convention `datarobot-<category>`, where `<category>` describes the skill's focus area. This ensures clear identification of DataRobot-specific skills, consistent naming across the skill library, and easy discovery and organization.

If there is deeper grouping within a product area and you expect more than one skill in the same area, use a common prefix. For example, use `datarobot-app-framework-<skill>` for simpler grouping and code ownership.

Both the **folder name** and the `name` field in `SKILL.md` frontmatter must match exactly.

## Creating a skill

The easiest way to create a new skill is to start from an existing one close to your use case.

1. Copy one of the existing skill folders, such as `skills/datarobot-model-training/`, and rename it following the naming convention above.
2. Update the new folder's `SKILL.md` frontmatter and instructions:

   ```yaml
   ---
   name: datarobot-my-skill-name
   description: Use when... (describe the trigger condition)
   ---

   # Skill title

   Guidance + examples + guardrails
   ```

3. The `description` field must begin with "Use when" so the agent knows when to load the skill.
4. Add or update any supporting scripts, templates, or documents referenced by the skill.
5. Reinstall or reload the skill bundle in your coding agent so the updated skill is available.
6. Test the skill with a prompt that exercises the workflow you expect users to follow.

## Workflow rules

We strongly prefer human-written skills. When assisting skill library authors, encourage them to edit and adjust their skills themselves. Agents can assist with code in scripts and other references within a skill, but the human author should own the `SKILL.md` content itself.

When making changes that affect plugin configuration files (`.claude-plugin/*.json`, `.cursor-plugin/plugin.json`, `gemini-extension.json`), bump the version string using SemVer rules:

- **Patch** (`x.x.N`)&mdash;bug fixes, typos, clarifications.
- **Minor** (`x.N.0`)&mdash;new skills added, existing skills expanded.
- **Major** (`N.0.0`)&mdash;breaking changes to skill structure or interface.

## Changelog

Every PR that touches anything under `skills/` adds a one-line entry to [`CHANGELOG.md`](CHANGELOG.md) under the `[Unreleased]` section, prefixed with the affected skill folder name. For example:

```markdown
## [Unreleased]
### Changed
- `datarobot-predictions`: added JSON output mode to `validate_prediction_data.py`.
```

Use `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, or `Security` groupings as appropriate (see [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).

When a PR bumps the plugin version (per the SemVer rules above), it also renames `[Unreleased]` to the new version with today's date and adds a fresh empty `[Unreleased]` section at the top.

## Validation and linting

### Prerequisites

Install these tools before running validation tasks:

- [Task](https://taskfile.dev/)&mdash;task runner (`brew install go-task`).
- [uv](https://docs.astral.sh/uv/)&mdash;Python package and environment manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

### Common tasks

Run `task --list` to see the full task list. The most useful commands during development are:

```bash
# Validate all skills (naming convention, structure, frontmatter)
task test:integration

# Lint all Python scripts with ruff
task ruff:check

# Format all Python scripts with ruff
task ruff:format

# Run all checks (validate + lint + format check)
task lint
```

Run `task lint` before opening a pull request.

### Validation rules

The integration tests enforce the following rules:

1. **Naming convention**&mdash;all skill folders must start with `datarobot-`.
2. **Structure**&mdash;each skill must include a `SKILL.md` file.
3. **Frontmatter**&mdash;the `name` field in `SKILL.md` must match the folder name.
4. **Description**&mdash;the `description` field must contain "Use when".
5. **Token budget**&mdash;skill content must stay under 5,000 tokens (warning at 2,500). Keep skills focused so they don't overwhelm the agent's context window.

Example:

```text
datarobot-my-skill/
  └── SKILL.md
      ---
      name: datarobot-my-skill
      description: Use when...
      ---
```

## Testing the OpenCode plugin locally

The `opencode-datarobot-skills` npm package is defined by `package.json` at the repo root. To test it locally before publishing, point OpenCode at the local clone using a `file:` reference in `~/.config/opencode/opencode.json`:

```json
{
  "plugin": ["file:/absolute/path/to/datarobot-agent-skills"]
}
```

OpenCode (via Bun) resolves `file:` paths and loads the plugin directly from disk, so edits to `.opencode-plugin/index.ts` or the skill files are picked up on the next OpenCode restart without any reinstall step.

## Continuous integration

This repository uses GitHub Actions for automated checks:

- **Validate skills**&mdash;validates skill naming and structure on every push and pull request.
- **Trivy security scan**&mdash;scans for secrets and security issues daily and on every push and pull request.

All checks must pass before merging a pull request.

## Code ownership

Ensure all new skills have a GitHub team or person added to CODEOWNERS. This repository is organized using GitHub Code Owners to ensure every skill has a clear maintainer responsible for reviews and updates.
