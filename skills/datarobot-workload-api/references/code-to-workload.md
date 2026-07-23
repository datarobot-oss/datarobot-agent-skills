# Code-to-Workload (C2W) — agent reference

The `dr` CLI subcommands referenced here (`dr artifact create`, `dr artifact code init`, `dr artifact code sync`, `dr artifact code versions`, `dr artifact code checkout`, `dr artifact build create`, `dr artifact build logs`, `dr artifact lock`, `dr workload create`, `dr workload get`, `dr workload logs`) ship in **dr CLI v0.2.74+** behind the `DATAROBOT_CLI_FEATURE_WORKLOAD=true` feature flag. Each step below also lists the raw HTTP fallback so the agent can drop down to the REST endpoints when the CLI isn't installed or when a flag is unset.

## When to reach for C2W

The user has source code but no published image. They cannot reach a registry DataRobot can pull from (no local Docker; no public registry account; the org admin hasn't pre-configured private-registry credentials). Image-pull credentials are NOT yet acceptable at workload creation, so C2W is the workaround: the platform builds the image and pushes it to DataRobot's internal registry, which workloads can pull from by default.

Don't use C2W when the user already has an image in an accessible registry — that's strictly more steps. Use the bring-your-own-image flow in SKILL.md section 1.

## Prerequisites the agent must surface

- `ENABLE_WORKLOAD_API_CONTAINERS=true` on the org (admin-set feature flag). If absent, `POST /artifacts/{id}/builds` returns a feature-flag error; the agent should fall back to bring-your-own-image or surface the gap to the user.
- `DATAROBOT_CLI_FEATURE_WORKLOAD=true` exported client-side, plus `DATAROBOT_ENDPOINT` and `DATAROBOT_API_TOKEN` already set.
- The `dr` CLI installed at **v0.2.74 or newer** (`https://github.com/datarobot-oss/cli`). Verify with `dr --version`. The `artifact` and `workload` namespaces are hidden until the feature flag is set, so a `dr --help` that doesn't list them just means the flag is missing.
- An Execution Environment with `sourceDockerImageUri` — used as the base image for the generated Dockerfile. See the next section for how to find one.

## Finding an Execution Environment

The C2W artifact spec needs `executionEnvironmentId` and `executionEnvironmentVersionId`. Discover via:

```shell
curl -sS "${DATAROBOT_ENDPOINT}/executionEnvironments/?limit=10" \
  -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" | jq '.data[] | {id, name, programmingLanguage, useCases, latestSuccessfulVersion: .latestSuccessfulVersion.id}'
```

The endpoint accepts these narrowing filters (all optional):

- **`useCases`** — one of `customModel | notebook | gpu | customApplication | sparkApplication | customJob`. The `GeneratedDockerfile` schema in the public spec does **not** constrain which `useCases` an EE must have to work with C2W (it only requires the EE to resolve to a base Docker image), and the upstream tutorial doesn't specify either. So use this filter only to narrow if the user has stated which surface they're targeting. Otherwise filter by `programmingLanguage` and `name` instead.
- **`searchFor`** — substring search on the EE's name + description.
- **`isPublic`** — boolean; restricts to platform-provided or user-created environments.

**Response shape:** envelope `{count, totalCount, data, next, previous}`; each `data[]` record has `id`, `name`, `programmingLanguage`, `isPublic`, `useCases`, `description`, `latestVersion`, `latestSuccessfulVersion`. **Use `latestSuccessfulVersion.id` for the EE version id** — `latestVersion` may point at a failed build. For more versions per EE: `GET /executionEnvironments/{id}/versions/?limit=10`.

> **Heads up — this endpoint requires the "Custom Environment" read permission** (separate from `Admin API` access). A regular user without it gets `403 {"message": "You do not have read permission for Custom Environment"}` even with `isPublic=true`. If the user hits this 403, ask them for the EE id + version id directly (their admin can provide them) rather than guess.

## Artifact spec with `imageBuildConfig`

The artifact created for a C2W flow is `draft` with `imageUri: "placeholder:latest"` — the build replaces it. The new fields versus a bring-your-own-image artifact:

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

Create it. CLI (v0.2.74+):

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

`dr artifact code init <artifact_id>` writes a `.wapi/` directory in the project root that tracks which artifact, catalog, and version this directory is bound to (conceptually similar to `.git/`). `dr artifact code sync` then:

1. Zips the project directory (respects `.dockerignore`).
2. Uploads the zip to the Files API as a new catalog version.
3. Waits for the catalog version to finish processing.
4. PATCHes the artifact's container spec to set `codeRef.datarobot.catalogId` and `codeRef.datarobot.catalogVersionId`.

`codeRef` on the container looks like:

```json
{"codeRef": {"datarobot": {"catalogId": "<id>", "catalogVersionId": "<vid>"}}}
```

If the CLI isn't available, the agent can reproduce sync manually: `POST /api/v2/files/fromFile/` with the zipped project, then `PATCH /artifacts/{id}/` with the container's `codeRef` set to the returned catalog id + version id.

## Triggering and watching a build

CLI (v0.2.74+) — when run from a directory linked via `dr artifact code init`, the artifact id is read from `.wapi/config.json` and can be omitted:

```shell
dr artifact build create                 # uses linked artifact
dr artifact build create <artifact_id>   # explicit
```

Raw fallback (empty body — `codeRef` on the artifact already tells the build system where to find the source):

```shell
curl -sS -X POST "${DATAROBOT_ENDPOINT}/artifacts/${ARTIFACT_ID}/builds" \
  -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" \
  -H "Content-Type: application/json" -d '{}'
```

Response: `202 Accepted` with `{"buildIds": ["<build_id>", ...]}`.

Poll with `python scripts/wait_for_build.py <artifact_id> <build_id>` (enforces the BUILT-vs-COMPLETED distinction below). The CLI's `dr artifact build get <build_id>` returns the current status if the agent wants a one-shot check rather than blocking polling.

**Build status progression — `BUILT` is NOT terminal-success:**

```
pending → in-progress → BUILT → COMPLETED       (or → FAILED)
```

- `BUILT` means the image was built locally on the build host but **has NOT been pushed to the registry yet**.
- `COMPLETED` means the image is built AND pushed to the registry — **only then is it deployable**.
- Scheduling a workload on an artifact whose build is `BUILT` (not yet `COMPLETED`) returns `422 runtime_image_uri ... None` because the registry can't resolve the imageUri yet.
- The gap between `BUILT` and `COMPLETED` can be **seconds to minutes** for large images.

So: **wait for `COMPLETED` specifically. Never trust `BUILT` as a green-light.** `wait_for_build.py` enforces this — `BUILT` keeps polling, only `COMPLETED` exits success.

C2W flows have also been observed reporting lowercase `pending` / `in-progress` / `completed` / `failed`. The poller's `.upper()` normalization treats `completed` and `COMPLETED` as equivalent terminal-success.

For real-time build logs, use `dr artifact build logs <build_id>` (v0.2.74+) or raw `GET /artifacts/{id}/builds/{bid}/logs` which returns **plain text** (not JSON) — the Docker build output. Read it when the user wants to see why a build failed.

After `COMPLETED`, the artifact's `imageUri` is populated automatically. Re-`GET` the artifact to confirm and surface the new image reference. Do not PATCH `imageUri` manually.

> **Known race condition (RAPTOR-17673):** even after `COMPLETED`, the image can briefly be unschedulable while the registry catches up — workload create returns `422 runtime_image_uri ... None`. If you hit this, wait a few seconds and retry the workload create. Platform-side fix in flight.

## `dockerfile.source` modes

- `generated` (default): the platform detects the project type (Python + uv lockfile is the documented case) and generates a Dockerfile using the Execution Environment's `sourceDockerImageUri` as the base. Installs dependencies from the lockfile and runs the `entrypoint` from `imageBuildConfig.dockerfile.entrypoint`. Recommended when the user has a standard project layout and no Dockerfile.
- `provided`: the user includes a `Dockerfile` at the project root. The build uses that file directly. Use when generated builds don't fit — custom system packages, multi-stage builds, non-Python projects.

The agent should default to `generated` unless the user explicitly asks otherwise or the project structure obviously requires it.

## Iteration loop

User edits source → `dr artifact code sync` → `dr artifact build create` → wait for `COMPLETED` → **redeploy the running workload onto the new build.**

`code sync` + `build create` keep the **same artifact ID** and only advance its `imageUri`; a running workload does **not** auto-adopt the rebuild until you redeploy. Redeploy the same draft with a rolling `PATCH /workloads/{wid}/settings/` (re-send the runtime body — even unchanged values roll it onto the latest `COMPLETED` build), or `POST /workloads/{wid}/replacement/` onto the same draft; switching to a *different* artifact is always a replacement. Full same-draft redeploy matrix and preconditions: `references/lifecycle-flows.md`.

Do **not** PATCH the artifact spec (env/probes) *between* `build create` and `COMPLETED` — it clobbers the pending `imageUri` auto-populate and you redeploy on the old image. Make spec edits before the build, or after `COMPLETED` with a fresh `GET`.

Each `dr artifact code sync` creates a new catalog version. Each build produces a new image. The artifact tracks the current image. `dr artifact code versions` lists the catalog versions for an artifact (i.e. its code history); `dr artifact code checkout <version_id>` downloads a previous version into `.wapi/.checkouts/` for read-only inspection or rollback.

## Locking for production

Once a draft artifact builds cleanly and the workload runs the way the user wants, `dr artifact lock <artifact_id>` (v0.2.74+) promotes the draft to **locked** — name, description, and spec become immutable, the artifact gets a version number, and it can never be deleted or unlocked. The CLI is the equivalent of `PATCH /artifacts/{id}/ {"status": "locked"}` and validates build completeness server-side: every container built from source must have its code uploaded and a build `COMPLETED`, otherwise the lock is rejected with a message naming the gap.

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

When the user is done experimenting and asks the agent to tear it all down (CLI v0.2.74+ in parens, raw REST also works):

1. `dr workload stop <wid>` (`POST /workloads/{wid}/stop`)
2. `dr workload delete <wid>` (`DELETE /workloads/{wid}`)
3. `dr artifact delete <aid>` (`DELETE /artifacts/{aid}`) — **only drafts can be deleted**; locked artifacts are permanent
4. Remove `.wapi/` from the project directory

Order matters: stop before delete on the workload; delete the workload before the artifact since the workload references it.
