# datarobot-skills-utils

Shared runtime utilities for the DataRobot agent skills in
[datarobot-agent-skills](https://github.com/datarobot-oss/datarobot-agent-skills).
Pure standard library, Python 3.11+.

## datarobot_skills_utils.opencode

LLM execution through the DataRobot CLI's opencode runtime, extracted from the
`datarobot-gap-analysis` and `datarobot-agent-assist` (swarm simulation) skills:

- `OpenCodeServer` — lifecycle of a private `dr opencode serve`: free random
  port, git-initialized isolated temp workdir (attached sessions take their
  project context from the server's cwd, and opencode's snapshotting needs a
  git repo), bounded health check, context-manager cleanup.
- `run_worker(...)` — one `dr opencode run` completion attached to a shared
  server (or in an isolated directory), with the anti-tool worker preamble,
  NUL/argv-size sanitization, and retry on empty output.
- `parse_events(...)` — parse the `--format json` JSONL event stream into the
  assistant text plus token/cost accounting; `strip_code_fences(...)` for
  JSON-contract consumers.

## Installation and versioning

Published to PyPI as `datarobot-skills-utils` by `.github/workflows/publish-pypi.yml`
on every GitHub release of this repo. The package has its own version (`version` in
`pyproject.toml`); bump it when the package changes, and the next release uploads it.
Releases that do not change the version skip the upload. Skills locate the package
through a small `_bootstrap.py` shim that tries, in order:

1. a sibling `packages/datarobot-skills-utils/src` directory (repo checkout, or a
   plugin install that copies `packages/` next to `skills/`), so local edits win;
2. an already installed distribution;
3. a one-time `pip install datarobot-skills-utils` (or `uv pip install` when the
   interpreter has no pip) into the running interpreter.

Running the shim directly (`python3 _bootstrap.py`) performs the same resolution
ahead of time and prints where the package was found.
