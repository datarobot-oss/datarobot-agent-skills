# `dr` CLI verb → Workload API route

Every `dr workload` and `dr artifact` verb, the route it calls, and what the
CLI adds over calling the route yourself. Confirmed against `dr` v0.12's
`--help`. Every verb takes `--output-format json` (stdout is then one JSON
document; warnings and hints go to stderr) and most take `--dir <path>` to
read the workload id from the nearest `.datarobot.yaml` instead of an
argument. `config`, `up` and `promote` are covered in depth in
`declarative-cli-deploy.md`.

## `dr workload`

| Verb | Route | Notes |
| --- | --- | --- |
| `config` | `GET /workloads/{id}/` with `--workload-id`; otherwise none | writes `.datarobot.yaml`; `--sync-env`, `--spec-file`, `--build-mode`, `--skip-env` |
| `up` | create, artifact PATCH, code sync, builds, `PATCH /settings/`, `POST /replacement/` as the plan needs | diff-and-apply from the manifest; `--dry-run`, `--yes`, `--promote`, `--force-build`, `--sync-env`, `--spec-file`, `--detach` |
| `promote` | `POST /workloads/{id}/promote/` | locks the running draft in place; 404 is also "not the artifact's owner" |
| `create --spec-file` | `POST /workloads/` | `--use-case-id`, `--enclave`; typed placement errors rendered with their code |
| `get` / `status` | `GET /workloads/{id}/` | `status` is the one-line form |
| `list` | `GET /workloads/` | |
| `start` / `stop` | `POST /workloads/{id}/start/`, `.../stop/` | accept `DATAROBOT_CLI_NON_INTERACTIVE=1` in place of `--yes` |
| `delete` | `DELETE /workloads/{id}/` | clears the manifest binding; `--purge` also removes the draft artifact, minted credentials and `.datarobot/workload/`; needs `--yes` when the id comes from the manifest |
| `endpoint` | `GET /workloads/{id}/` | prints the URL the edge serves |
| `settings` | `GET` / `PATCH /workloads/{id}/settings/` | `--replicas N` (`--group` with several groups), `--spec-file` for a whole settings body, `--wait` follows the rollout |
| `diagnose` | `GET /workloads/{id}/` status details per replica and container | verdict plus findings for `CrashLoopBackOff`, `ImagePullBackOff`, `ErrImagePull`, `OOMKilled`, non-zero exits, restarts; exit 0 on an errored workload; `{"diagnosis": …}` in JSON. CLI equivalent of `scripts/diagnose_workload.py` |
| `events` | `GET /workloads/{id}/events/` | oldest first; `--type` (repeatable substring), `--since`/`--until`, `--proton-id`, `--limit` |
| `logs` | `GET /otel/workload/{id}/logs/` | `--level` (minimum severity), `--grep`/`--exclude` (repeatable, case-insensitive), `--trace-id`, `--span-id`, `--since`/`--until` (RFC 3339, a date, or `15m`/`2h`/`1d`/`1w`), `--limit`, `--follow`. Proton-scoped logs still need REST (`searchKeys=proton_id`). An empty result points at `diagnose` |

## `dr artifact`

| Verb | Route | Notes |
| --- | --- | --- |
| `create --spec-file` | `POST /artifacts/` | |
| `get` / `list` / `delete` | `GET`, `GET`, `DELETE /artifacts/{id}/` | delete answers 409 while a workload runs the artifact |
| `lock` | `PATCH /artifacts/{id}/ {"status":"locked"}` | one-way; already locked answers 403 |
| `code init <artifact-id>` | file catalog binding | writes `.datarobot/workload/config.json`; `--dir`, `--yes` |
| `code sync` | `POST /api/v2/files/fromFile/` + `PATCH /artifacts/{id}/` `codeRef` | two-way by default; `--dry-run`, `--diff`, `--push-only` (upload only, refuse conflicts, never touch local files), `--accept-remote` |
| `code versions` / `code checkout` | catalog versions | read-only snapshot under `.datarobot/workload/.checkouts/` |
| `build create` | `POST /artifacts/{id}/builds/` | `--wait` polls to `COMPLETED`/`FAILED`/`CANCELLED` and prints the image URI; treat `CANCELLED` like `FAILED` |
| `build get` / `build list` / `build logs` | `GET /artifacts/{id}/builds/…` | `build get --wait` for an already-running build |

## Reading errors

A `403` on the very first request, including `dr workload list`, is the
platform's Workload API entitlement, not the CLI. `404` from
`promote` can mean the caller does not own the artifact. The CLI renders
typed placement errors as the server's sentence plus the machine code in
parentheses, e.g. `(MISSING_USE_CASE)`, `(ENCLAVE_TARGETING_REQUIRED)`.
