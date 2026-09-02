# Contributing guidelines

Guidelines for developing and contributing to this project.

## List of project maintainers

This project is maintained by the following people:

- [Your Name](Your GitHub User URL)

## Open a new issue

Follow these steps before opening a new issue:

- Before opening a new issue, check if there are any existing FAQ entries (if one exists), issues, or pull requests that match the issue.
- Open an issue and label it accordingly—bug, improvement, feature request, etc.
- Be as specific and detailed as possible.

## Did you find a bug?

Follow these steps when reporting a bug:

- Do not open a GitHub issue if the bug is a security vulnerability. Instead, email the maintainers directly or email oss-community-management@datarobot.com if they do not respond within seven days.
- Ensure the bug was not already reported in the project's Issues section.
- Open an issue as described in [Open a new issue](#open-a-new-issue).

## Run e2e skill tests

Skill quality is evaluated end-to-end by an LLM judge. To keep CI cheap, unchanged skills are skipped via an MD5 cache at `tests/e2e/skill_hashes.json`.

### Local pre-commit hook (recommended)

Run once after cloning:

```bash
cp .env.example .env  # fill in DATAROBOT_ENDPOINT + DATAROBOT_API_TOKEN
task setup            # installs .githooks/ as the project hooks path
```

After that, any commit touching `skills/**` or `tests/e2e/**` runs the LLM judge on the affected skills and—if they pass—stages the refreshed `skill_hashes.json` into the same commit. By the time the PR hits CI, the hashes already match and the e2e job is a no-op for those skills.

If `DATAROBOT_ENDPOINT` / `DATAROBOT_API_TOKEN` aren't set, the hook prints a notice and skips; CI runs the judge as a safety net. To bypass the hook for a single commit: `git commit --no-verify`.

### Run the suite manually

```bash
task test:e2e         # or: uv run --group e2e pytest tests/e2e/ -v
task test:e2e:force   # re-evaluate every skill, ignore the cache
```

CI does not write back to `main`; if the committed cache drifts the workflow logs a warning, and the fix is to run the command above locally and commit the refreshed file.

## Respond to issues and pull requests

The project maintainers make every effort to respond to open issues as soon as possible.

If a response doesn't arrive within seven days of creating an issue or pull request, send an email to oss-community-management@datarobot.com.

## Should I add a skill here?

Evaluate a new skill against the following goal, intended use, and criteria before adding it to this library.

### Goal

The goal of this library is to ensure that enterprises can get agents into production. Skills offer powerful functionality that tells agents how to think while protecting their context window. This allows agents to one- or few-shot tasks that previously needed complex logic built into the agent, avoiding context window issues. Skills DataRobot offers open up enterprise use cases, making them more viable in production.

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

If there is deeper grouping within a product area and more than one skill is expected in the same area, use a common prefix. For example, use `datarobot-app-framework-<skill>` for simpler grouping and code ownership.

Both the **folder name** and the `name` field in `SKILL.md` frontmatter must match exactly.

## Create a skill

The easiest way to create a new skill is to start from an existing one close to the intended use case.

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
5. Add an entry for the new skill in `.well-known/ai-catalog.json`. Copy an existing entry and update the `identifier`, `displayName`, `url`, `description`, and `representativeQueries` fields. Write `representativeQueries` as natural-language phrases a user would type to discover the skill—these drive semantic search quality in ARD discovery services.
6. Reinstall or reload the skill bundle in the coding agent so the updated skill is available.
7. Test the skill with a prompt that exercises the expected user workflow.

## Workflow rules

DataRobot strongly prefers human-written skills. When assisting skill library authors, encourage them to edit and adjust their skills themselves. Agents can assist with code in scripts and other references within a skill, but the human author owns the `SKILL.md` content itself.

**PRs never bump the shared plugin version themselves.** The version is shared across `package.json`, `.claude-plugin/*.json`, `.cursor-plugin/plugin.json`, and `gemini-extension.json`. When a PR that changes anything under `skills/` merges to `main`, [`version-bump.yml`](.github/workflows/version-bump.yml) automatically bumps all of those files to the same new value, renames `CHANGELOG.md`'s `[Unreleased]` section, commits, tags, and cuts a GitHub Release&mdash;see [`scripts/version_bump.py`](scripts/version_bump.py).

Every merge bumps **minor** (`x.N.0`) by default&mdash;this is a skills/marketplace repo where any merge under `skills/` is effectively new content. **Major** (`N.0.0`, breaking changes to skill structure or interface) is never inferred automatically; if a change is genuinely breaking, bump and tag it by hand instead of relying on the automated flow. **Patch** (`x.x.N`) is also manual&mdash;used to hot-fix a version that's already sealed into a product build, without moving the marketplace's current minor line forward:

```bash
task version:bump -- --bump patch
```

`packages/datarobot-skills-utils` is versioned on its own (`version` in its `pyproject.toml`, starting at 0.1.0) and is not touched by the automated bump. Bump it in the PR that changes the package; every GitHub Release then runs `publish-pypi.yml`, which uploads that version to PyPI and skips silently when it is already published.

## Changelog

Every PR that touches anything under `skills/` adds a one-line entry to [`CHANGELOG.md`](CHANGELOG.md) under the `[Unreleased]` section, prefixed with the affected skill folder name, under one of `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, or `Security` (see [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)). The category header is required, not optional&mdash;always nest the bullet under one. For example:

```markdown
## [Unreleased]
### Changed
- `datarobot-predictions`: added JSON output mode to `validate_prediction_data.py`.
```

Don't rename `[Unreleased]` manually&mdash;`version-bump.yml` does that automatically once the PR merges (see "Plugin version management" above). A PR that changes `skills/` but leaves `[Unreleased]` empty merges fine, but the automated release fails loudly instead of shipping a version bump with no changelog entry; fix it by adding the missing entry.

## Validation and linting

This section covers the prerequisites, common tasks, and rules enforced by this repository's validation and linting tooling.

### Prerequisites

Install these tools before running validation tasks:

- [Task](https://taskfile.dev/)&mdash;task runner (`brew install go-task`).
- [uv](https://docs.astral.sh/uv/)&mdash;Python package and environment manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
- [license-eye](https://github.com/apache/skywalking-eyes)&mdash;license header checker (`go install github.com/apache/skywalking-eyes/cmd/license-eye@latest`, then ensure `~/go/bin` is on the PATH).
- [jq](https://jqlang.org/)&mdash;JSON processor used by `scripts/version_bump.py` (`brew install jq`).

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

## Test the OpenCode plugin locally

The `opencode-datarobot-skills` npm package is defined by `package.json` at the repo root. To test it locally before publishing, point OpenCode at the local clone using a `file:` reference in `~/.config/opencode/opencode.json`:

```json
{
  "plugin": ["file:/absolute/path/to/datarobot-agent-skills"]
}
```

OpenCode (via Bun) resolves `file:` paths and loads the plugin directly from disk, so edits to `.opencode-plugin/index.ts` or the skill files are picked up on the next OpenCode restart without any reinstall step.

## Continuous integration

This repository uses GitHub Actions for automated checks:

- **Lint**&mdash;runs `task lint` (skill validation, ruff, mypy, shellcheck, yamlfmt, license headers) on every push and pull request.
- **Test Skills E2E**&mdash;runs the LLM-judge skill quality suite on pushes/PRs that touch `skills/**` or `tests/e2e/**`.
- **Trivy security scan**&mdash;scans for secrets and security issues daily and on every push and pull request.
- **Version Bump**&mdash;on every push to `main`, bumps the plugin version, tags, and cuts a GitHub Release if `skills/` changed (see "Plugin version management" above).
- **Publish to npm**&mdash;publishes to npm whenever a GitHub Release is published.
- **Publish AI Catalog**&mdash;deploys `docs/` to GitHub Pages when it changes on `main`.

All required checks must pass before merging a pull request.

## Code ownership

Ensure all new skills have a GitHub team or person added to CODEOWNERS. This repository is organized using GitHub Code Owners to ensure every skill has a clear maintainer responsible for reviews and updates.
