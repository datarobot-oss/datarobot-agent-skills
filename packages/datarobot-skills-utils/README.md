# datarobot-skills-utils

Runtime utilities for running LLM calls through the DataRobot CLI's `dr opencode`
runtime, used by the DataRobot agent skills in
[datarobot-agent-skills](https://github.com/datarobot-oss/datarobot-agent-skills).

> **Beta.** This package exists to support the DataRobot agent skills. Its API may change
> between minor versions without notice, and it carries no official support. Pin an exact
> version if you depend on it.

## Prerequisites

- Python 3.11 or later. The package has no third-party dependencies.
- The [DataRobot CLI](https://github.com/datarobot-oss/cli) (`dr`) on your `PATH`, logged in
  with `dr auth login`. Every LLM call goes through `dr opencode`, so the CLI's login and
  model access apply.

## Installation

```bash
pip install datarobot-skills-utils
```

## Example

Start one private `dr opencode serve` for a batch of calls, send a prompt, and read the
token usage:

```python
from datarobot_skills_utils.opencode import (
    OpenCodeServer,
    UsageMeter,
    dr_available,
    run_worker,
)

model = "datarobot/anthropic/claude-sonnet-4-6"  # any model listed by `dr opencode models`

if not dr_available():
    raise SystemExit("The DataRobot CLI (dr) is not on PATH.")

usage = UsageMeter(model)
with OpenCodeServer(models=[model], reasoning="max") as server:
    text, meta = run_worker(
        "Name three risks of hard-coding API keys.",
        model,
        server_url=server.url,
        cwd=server.workdir,
    )
    usage.record(meta)

print(text)
print(usage.snapshot()["total"])  # calls, input/output/reasoning/cache tokens, cost
```

## API

Everything is exported from `datarobot_skills_utils.opencode`.

- `OpenCodeServer(models=(), reasoning=None)`: a private `dr opencode serve` on a free
  localhost port, in an isolated temporary working directory. Use it as a context manager;
  `url` and `workdir` are set while it runs. Passing `models` and `reasoning` (`"max"`,
  `"off"`, or a specific effort) sets the reasoning effort and output-token limits for those
  models without editing your `opencode.json`.
- `run_worker(message, model, server_url=None, cwd=None, timeout=120, attempts=2, ...)`: one
  `dr opencode run` completion, attached to a server or run standalone. Returns
  `(text, token_meta)`, and retries an empty response.
- `UsageMeter(model, reasoning_effort=None)`: thread-safe token and cost accounting across a
  run. Set `phase` before a batch, call `record(meta)` after each call, and read totals with
  `snapshot()`.
- `parse_events(stdout)` and `strip_code_fences(text)`: parse `dr opencode run --format json`
  output into text plus token accounting, and strip Markdown fences from JSON replies.
- `dr_available()`, `worker_env(...)`, `resolve_effort(...)`, `max_reasoning_effort(...)`,
  `token_limits(...)`: helpers for checking the CLI and resolving per-model reasoning effort
  and output limits.

## License

Apache License 2.0. See
[LICENSE](https://github.com/datarobot-oss/datarobot-agent-skills/blob/main/packages/datarobot-skills-utils/LICENSE).
