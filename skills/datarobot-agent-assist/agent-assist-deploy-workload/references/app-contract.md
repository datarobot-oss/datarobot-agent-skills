# Make the app deployable

This skill doesn't build the agent. It deploys the code that's already in `<target_dir>`. If there's no agent code yet, send the user to agent assist option 2 first.

Read the code and check it against the list below. Fix anything that doesn't match yourself, keeping changes to what the deploy needs. Don't rewrite the agent's logic, tools or framework. If the code can't be made to run as one process on one port without rewriting the agent, switch to the Pulumi path in [deploy-path.md](deploy-path.md) and stop.

- One Python project: `pyproject.toml` and a current `uv.lock`. Run `uv lock` after every dependency change. The platform builds from the lockfile.
- One web server on port 8080 that serves the agent, its API and its UI. Note the entry point (for example `app:app`); SKILL.md section 3 needs it.
- `GET /healthz` returns 200 with no auth and no LLM call. Probes hit the container directly. Add it if it's missing.
- The LLM is called through the LLM Gateway, reading `DATAROBOT_ENDPOINT` and `DATAROBOT_API_TOKEN` from the environment.
- Tool secrets come from env vars. Names go in code, values never do. Follow agent assist's `.env` rules: append `NAME=` to `<target_dir>/.env` and never read the file yourself. Tell the user exactly what to do, for example: "Open the file `.env` in your project folder, find the line `SOME_TOOL_API_KEY=`, paste your key right after the `=`, and save. Don't paste the key here in the chat."
- Serve under the workload prefix. Users reach the app at `/api/v2/endpoints/workloads/<id>/`. The edge strips that prefix before the request reaches the container and doesn't rewrite responses, so every URL the app emits (links, assets, fetch calls, redirects) has to carry it. Build it at startup from the injected `WORKLOAD_ID` and pass it as FastAPI `root_path`:
  ```python
  wid = os.environ.get("WORKLOAD_ID")
  PREFIX = f"/api/v2/endpoints/workloads/{wid}" if wid else ""
  ```
  In the frontend use relative URLs or the prefix. Never a URL starting with `/`. Locally `WORKLOAD_ID` is unset, so the app runs at `/`.
- Who is calling. The edge requires a DataRobot login, then sets `X-Datarobot-User-Id`, `X-Datarobot-Username`, `X-User-Email` and `X-Datarobot-Org-Id` on every request, overwriting whatever the caller sent. Trust those. Don't trust `X-Datarobot-Identity-Token`: a forged value passes through unchanged and there's no published way to verify it. If the spec limits who can use the agent, check `X-User-Email` against an allowlist. Remove any login page.
- The frontend must never send an `Authorization` header to its own backend. The edge treats it as a DataRobot API key and rejects the request before it reaches the container.
- Log to stdout.

Tell the user in one plain sentence what you changed, for example: "I made a few small changes so your agent works on DataRobot."
