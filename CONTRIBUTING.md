# Contributing Guidelines

Guidelines for developing and contributing to this project.

## List of project maintainers

- [Your Name](Your GitHub User URL)


## Opening new issues

- Before opening a new issue check if there are any existing FAQ entries (if one exists), issues or pull requests that match your case
- Open an issue, and make sure to label the issue accordingly - bug, improvement, feature request, etc...
- Be as specific and detailed as possible

## Did you find a bug?

- Do not open up a GitHub issue if the bug is a security
vulnerability, instead email the maintainers directly or email
oss-community-management@datarobot.com if they do not respond within
seven days
- Ensure the bug was not already reported in the projects Issues section
- Open an issue as described above

## Running e2e skill tests

Skill quality is evaluated end-to-end by an LLM judge. To keep CI cheap, unchanged skills are skipped via an MD5 cache at `tests/e2e/skill_hashes.json`.

If you change a skill, run the suite locally before pushing and commit the refreshed hash file alongside your skill changes:

```
cp .env.example .env  # fill in DATAROBOT_ENDPOINT + DATAROBOT_API_TOKEN
task test:e2e         # or: uv run --group e2e pytest tests/e2e/ -v
git add tests/e2e/skill_hashes.json
```

Force a full re-evaluation (ignore the cache) with `task test:e2e:force`.

CI does not write back to `main`; if the committed cache drifts, the workflow logs a warning and the fix is to run the command above locally and open a PR.

## Responding to issues and pull requests

This project's maintainers will make every effort to respond to any
open issues as soon as possible.

If you don't get a response within seven days of creating your issue or
pull request, please send us an email at oss-community-management@datarobot.com
