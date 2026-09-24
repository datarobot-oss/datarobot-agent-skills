# Code-to-Workload (C2W) — agent reference

The `dr` CLI subcommands referenced here (`dr artifact create`, `dr artifact code init`, `dr artifact code sync`, `dr artifact code versions`, `dr artifact code checkout`, `dr artifact build create`, `dr artifact build logs`, `dr artifact lock`, `dr workload create`, `dr workload get`, `dr workload logs`) are GA on a current CLI (confirmed on `dr` v0.9.0). Don't gate on a hardcoded minimum version — see SKILL.md's Prerequisites for why — and run `dr self update --force` before assuming a command is unsupported. Each step below also lists the raw HTTP fallback for when the CLI isn't installed.

## When to reach for C2W

User has source but no published image, and can't reach a pullable registry (no local Docker, no public registry account, no admin-configured private-registry creds). Image-pull creds not yet accepted at workload creation — C2W workaround: platform builds the image, pushes to DataRobot's internal registry, workloads pull from it by default.

Skip C2W if an image already exists in an accessible registry — more steps for no gain. Use SKILL.md section 1's bring-your-own-image flow.

## Prerequisites the agent must surface

- `ENABLE_WORKLOAD_API_CONTAINERS=true` on the org (admin-set, server-side, unrelated to CLI version; not re-verified this session). Absent: `POST /artifacts/{id}/builds` returns a feature-flag error — fall back to bring-your-own-image or surface the gap.
- `DATAROBOT_ENDPOINT` and `DATAROBOT_API_TOKEN` already set.
- The `dr` CLI, kept current (`https://github.com/datarobot-oss/cli`). Run `dr self update --force` before a C2W flow rather than trusting a pinned version — see SKILL.md's Prerequisites. If `dr --help` doesn't list `artifact`/`workload` after updating, the CLI is too old.
- An Execution Environment with `sourceDockerImageUri` (base image for the generated Dockerfile) — next section covers finding one.

## Finding an Execution Environment

Artifact spec needs `executionEnvironmentId` + `executionEnvironmentVersionId`. Discover via:

```shell
curl -sS "${DATAROBOT_ENDPOINT}/executionEnvironments/?limit=10" \
  -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" | jq '.data[] | {id, name, programmingLanguage, useCases, latestSuccessfulVersion: .latestSuccessfulVersion.id}'
```

Optional narrowing filters:

- **`useCases`** — one of `customModel | notebook | gpu | customApplication | sparkApplication | customJob`. `GeneratedDockerfile`'s public schema does **not** restrict which `useCases` an EE needs for C2W (only requires it resolve to a base Docker image); the upstream tutorial doesn't specify either. Use this filter only if the user names a target surface — otherwise filter by `programmingLanguage`/`name`.
- **`searchFor`** — substring search on the EE's name + description.
- **`isPublic`** — boolean; restricts to platform-provided or user-created environments.

**Response shape:** envelope `{count, totalCount, data, next, previous}`; each `data[]` record has `id`, `name`, `programmingLanguage`, `isPublic`, `useCases`, `description`, `latestVersion`, `latestSuccessfulVersion`. **Use `latestSuccessfulVersion.id` for the EE version id** — `latestVersion` may point at a failed build. More versions per EE: `GET /executionEnvironments/{id}/versions/?limit=10`.

> **Needs "Custom Environment" read permission** (separate from `Admin API`). Without it: `403 {"message": "You do not have read permission for Custom Environment"}`, even with `isPublic=true`. On this 403, ask the user for the EE id + version id (their admin can provide) rather than guess.

## Artifact spec with `imageBuildConfig`

C2W artifact starts `draft`, `imageUri: "placeholder:latest"` (build replaces it). New fields vs. bring-your-own-image:

```json
{
  "name": "<artifact-name>",
  "type": "service",
  "spec": {
    "containerGroups": [{
      "containers": [{
        "name": "primary",
        "imageUri": "placeholder:latest",
        "primary": true,
        "port": 8080,
        "imageBuildConfig": {
          "dockerfile": {
            "source": "generated",                            // or "provided"
            "executionEnvironmentId": "<EE_ID>",              // required when source=generated
            "executionEnvironmentVersionId": "<EE_VERSION_ID>",
            "entrypoint": ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
          }
        },
        "readinessProbe": {
          "path": "/version", "port": 8080,
          "initialDelaySeconds": 10, "periodSeconds": 10,
          "timeoutSeconds": 5, "failureThreshold": 6, "scheme": "HTTP"
        }
      }]
    }]
  }
}
```

Create: CLI (recent `dr` — see Prerequisites):

```shell
dr artifact create --spec-file /tmp/spec.json --output-format json
```

Raw fallback:

```shell
curl -sS -X POST "${DATAROBOT_ENDPOINT}/artifacts/" \
  -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" \
  -H "Content-Type: application/json" --data @/tmp/spec.json
```

## Linking a project directory + syncing source

`dr artifact code init <artifact_id>` (`--dir <path>` for a non-cwd target; `--yes` skips the directory prompt) writes a **`.datarobot/workload/`** state directory at the project root, tracking the bound artifact/catalog/version (like `.git/`) — **not `.wapi/`**, a stale name (confirmed against `dr` v0.9.0's `--help`; re-verify on a different CLI version).

`dr artifact code sync` (`--dry-run`: preview, no writes; `--diff`: per-file unified diffs; `--yes`: skip confirmation) computes a **three-way diff** against the last synced state and applies it in one step — not a blind re-zip-and-upload. Conflicts auto-resolve **remote wins**; the conflicting local version is saved as `*.LOCAL.<timestamp>`, not discarded. Under the hood:

1. Zips the project directory (respects `.dockerignore`).
2. Uploads the zip to the Files API as a new catalog version.
3. Waits for the catalog version to finish processing.
4. PATCHes the artifact's container spec to set `imageBuildConfig.codeRef.datarobot.catalogId` and `imageBuildConfig.codeRef.datarobot.catalogVersionId`.

**`codeRef` lives under `imageBuildConfig`, not directly on the container** (observed at `containers[]` top level):

```json
{"imageBuildConfig": {"codeRef": {"datarobot": {"catalogId": "<id>", "catalogVersionId": "<vid>"}}}}
```

> **Confirmed footgun: a misplaced `codeRef` (e.g. directly on the container, not under `imageBuildConfig`) is silently accepted and dropped by `PATCH /artifacts/{id}/` — no 400.** `POST /builds` then fails: "No codeRef with catalog identifiers found" — a wasted round trip. After any `codeRef` PATCH, re-`GET` and confirm `imageBuildConfig.codeRef` landed (verify against your cluster's live schema — this field has already moved once) before building. General rule: `GET` includes read-only fields (`build`, `imageOutdated`, `routes`, `securityContext`, …) that must be stripped before PATCHing back; PATCH drops unknown/misplaced fields instead of rejecting them.

Without the CLI: `POST /api/v2/files/fromFile/` with the zipped project, then `PATCH /artifacts/{id}/` setting `imageBuildConfig.codeRef` to the returned catalog id + version id — verify via a follow-up `GET`.

## Triggering and watching a build

CLI (recent `dr` — see Prerequisites); from a linked directory, artifact id is read from `.datarobot/workload/config.json` and can be omitted:

```shell
dr artifact build create                 # uses linked artifact; prints buildIds and returns
dr artifact build create <artifact_id>   # explicit
dr artifact build create --wait          # CLI polls to a terminal status itself (COMPLETED/FAILED/CANCELLED) and prints a summary + image_uri
```

Raw fallback (empty body — artifact's `codeRef` already tells the build system where the source is):

```shell
curl -sS -X POST "${DATAROBOT_ENDPOINT}/artifacts/${ARTIFACT_ID}/builds" \
  -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" \
  -H "Content-Type: application/json" -d '{}'
```

Response: `202 Accepted` with `{"buildIds": ["<build_id>", ...]}`.

On the CLI: `dr artifact build create --wait` (or `build get <build_id> --wait`) polls to a terminal status natively, dumps the log tail on failure. On raw REST (or to enforce the BUILT-vs-COMPLETED distinction explicitly): `python scripts/wait_for_build.py <artifact_id> <build_id>`. `build get <build_id>` (no `--wait`) gives a one-shot status.

**Build status progression — `BUILT` is NOT terminal-success:**

```
pending → in-progress → BUILT → COMPLETED       (or → FAILED)
```

- `BUILT` means the image was built locally on the build host but **has NOT been pushed to the registry yet**.
- `COMPLETED` means the image is built AND pushed to the registry — **only then is it deployable**.
- Scheduling a workload on an artifact whose build is `BUILT` (not yet `COMPLETED`) returns `422 runtime_image_uri ... None` because the registry can't resolve the imageUri yet.
- The gap between `BUILT` and `COMPLETED` can be **seconds to minutes** for large images.

**Wait for `COMPLETED` specifically — never trust `BUILT` as a green-light.** `wait_for_build.py` enforces this: `BUILT` keeps polling, only `COMPLETED` exits success. CLI `--wait` also recognizes **`CANCELLED`** as terminal — treat it like `FAILED`.

C2W also reports lowercase `pending`/`in-progress`/`completed`/`failed`. The poller's `.upper()` normalization treats `completed` = `COMPLETED`.

Build logs: `dr artifact build logs <build_id>` returns a **structured JSON stream**, `INFO`+ by default (`--level debug` for all) — not raw Docker output. For raw Docker build output: `GET /artifacts/{id}/builds/{bid}/logs` returns **plain text**. Read either to diagnose a failed build.

After `COMPLETED`, `imageUri` auto-populates. Re-`GET` to confirm and surface it. Never PATCH `imageUri` manually.

> **Known race (RAPTOR-17673):** even after `COMPLETED`, the image can briefly be unschedulable while the registry catches up — workload create returns `422 runtime_image_uri ... None`. Wait a few seconds, retry. Platform fix pending.

## `dockerfile.source` modes

- `generated` (default): platform detects project type (Python + uv lockfile is the documented case), generates a Dockerfile from the EE's `sourceDockerImageUri`, installs from the lockfile, runs `entrypoint` from `imageBuildConfig.dockerfile.entrypoint`. Use for a standard layout with no Dockerfile.
- `provided`: user's own `Dockerfile` at project root, used directly. Use when `generated` doesn't fit — custom system packages, multi-stage builds, non-Python.

Default to `generated` unless the user asks otherwise or the project clearly needs `provided`.

## Iteration loop

> **Consider `dr workload up` instead of the steps below.** With a committed (or committable) `.datarobot.yaml`, `up` collapses this loop — sync, build, wait, redeploy — into one command, skipping the build when nothing changed. See `references/declarative-cli-deploy.md`. Use the manual loop for scripting outside that convention or to inspect intermediate build/artifact state.

User edits source → `dr artifact code sync` → `dr artifact build create` → wait for `COMPLETED` → **redeploy the running workload onto the new build.**

`code sync` + `build create` keep the **same artifact ID**, only advance `imageUri`; a running workload does **not** auto-adopt the rebuild until redeployed. Redeploy the same draft: rolling `PATCH /workloads/{wid}/settings/` (re-send the runtime body — even unchanged, rolls onto the latest `COMPLETED` build), or `POST /workloads/{wid}/replacement/` onto the same draft. Switching to a *different* artifact is always a replacement. Full matrix: `references/lifecycle-flows.md`.

Never PATCH the spec (env/probes) *between* `build create` and `COMPLETED` — clobbers the pending `imageUri` auto-populate, redeploys the old image. Edit before the build, or after `COMPLETED` with a fresh `GET`.

Each `sync` creates a new catalog version; each build a new image. Artifact tracks the current image. `dr artifact code versions` (`--limit N`) lists catalog versions (code history), marking the artifact's current `codeRef` with `*`. `dr artifact code checkout [<version_id>]` (optional, prompts if omitted, accepts an id prefix; `--clean` removes checkouts instead of downloading) downloads a version into `.datarobot/workload/.checkouts/<version-id>/` for read-only inspection or rollback — doesn't touch the working directory or sync-state.

## Locking for production

Once a draft builds cleanly and the workload behaves as wanted: `dr artifact lock <artifact_id>` (recent `dr` — see Prerequisites) promotes to **locked** — name/description/spec immutable, versioned, never deletable or unlockable. Equivalent to `PATCH /artifacts/{id}/ {"status": "locked"}`; validates build completeness server-side (every source-built container needs uploaded code + `COMPLETED` build), else rejects with the gap named.

## Failure modes the agent should recognize

| Symptom | Likely cause | Action |
|---|---|---|
| `POST /builds/` returns a feature-flag error | `ENABLE_WORKLOAD_API_CONTAINERS=false` on the org | Surface to user; fall back to bring-your-own-image if they have an alternative |
| Build status `failed` with "lock file mismatch" in logs | `pyproject.toml` updated but `uv.lock` wasn't regenerated | User runs `uv lock` locally, `dr artifact code sync` again, new build |
| Build status `failed` with "unreachable base image" in logs | EE's `sourceDockerImageUri` not pullable from the build host | Try a different EE, or report to admin |
| Build status `failed` with missing-dependency error | `pyproject.toml` doesn't list a required package | User adds dependency, `uv lock`, sync, rebuild |
| Build status stuck on `in-progress` past 5 min for small projects | Build queue contention or platform-side delay | Continue polling; check `/builds/{bid}/logs/` for output progress |
| Artifact `imageUri` still `"placeholder:latest"` after build `completed` | Build succeeded but artifact write didn't propagate (rare) | Re-`GET` the artifact; if still placeholder, file a platform bug |
| `POST /workloads/` returns `422 runtime_image_uri ... None` after `COMPLETED` | Race condition (RAPTOR-17673): registry hasn't caught up post-push | Wait a few seconds and retry. Don't treat `BUILT` as deployable — that's the most common cause of this 422 |

## State map

| Where | What |
|---|---|
| Artifact `imageUri` | Set to `"placeholder:latest"` on create; populated by the build on success |
| Artifact `imageBuildConfig` | Persists across rebuilds; the build instruction set |
| Artifact `codeRef` | Pointer to the catalog version with source code; updated each `dr artifact code sync` |
| Catalog versions | Immutable snapshots of synced source; listed by `dr artifact code versions` |
| Builds | `POST /artifacts/{id}/builds/` produces one; listed by `GET /artifacts/{id}/builds/` |
| Workload | References artifact by `artifactId`; runs whatever image the artifact currently points at |

## Cleanup sequence

Tear-down, on request (CLI in parens, kept current per Prerequisites; raw REST also works):

1. `dr workload stop <wid>` (`POST /workloads/{wid}/stop`)
2. `dr workload delete <wid>` (`DELETE /workloads/{wid}`)
3. `dr artifact delete <aid>` (`DELETE /artifacts/{aid}`) — **only drafts can be deleted**; locked artifacts are permanent
4. Remove `.datarobot/workload/` from the project directory

Order matters: stop before delete (workload); delete workload before artifact (workload references it).
