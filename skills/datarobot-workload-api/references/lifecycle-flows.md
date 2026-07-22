# Artifact lifecycle — rules the spec doesn't state

The SKILL.md section 4 has the operational summary and example code. This reference holds **only the behavioral rules** that aren't visible from the spec alone (`POST /artifacts/`, `PATCH /artifacts/{id}/`, etc. shapes are in the spec).

## Lifecycle states and transitions

```
create  →  iterate (PATCH while draft)  →  lock  →  rolling replacement
              ↳ status=draft                ↳ status=locked, immutable
                                              clones create new drafts
```

- Artifacts start in `draft` when created.
- While `draft`: PATCH applies in place.
- When `locked`: artifact becomes immutable. Any edit requires `POST /artifacts/{id}/clone/` (produces a new draft in the same artifact repository), then PATCH on the clone.
- Once locked, to deploy changes you trigger a **rolling replacement** on the workload (`POST /workloads/{wid}/replacement/`). Promote is the alternative for the in-place draft→locked case.

## Replacement preconditions — two rejections agents hit

`POST /workloads/{id}/replacement/` enforces **two** preconditions the spec doesn't spell out. Both must hold or the call is rejected:

1. **The candidate must be a DIFFERENT artifact than the one running.** Passing the current `artifactId` (e.g. after PATCH-ing or rebuilding the draft the workload already runs) returns **HTTP 422**: `{"detail": ["Cannot replace with the same artifact — candidate artifact ID matches current artifact."]}`. Replacement means "swap to another artifact version" — it is never how you apply an in-place edit to the current one.
2. **Status must match.** **HTTP 400** `{"detail": "Artifact status mismatch: ..."}` unless the candidate's status matches the running artifact's.

| Workload currently runs | Goal | Do this |
|---|---|---|
| draft | apply an in-place change (env/probes/port or a new build) to the **same** draft | PATCH/rebuild that draft, then `stop` → `start` (NOT replacement — same artifact ID 422s) |
| draft | zero-downtime swap | clone or create a **new** draft, change it, build it, `POST /replacement/` onto the **new** draft (draft↔draft) |
| draft | lock the same artifact in place | `POST /workloads/{id}/promote/` (no restart) |
| locked | deploy new content | clone → patch the draft → lock the new draft → `POST /replacement/` onto the clone (locked↔locked) |

Neither rule is in the spec's path docs — agents have to know them from the error responses or from this reference. There is no `dr workload replacement` CLI subcommand; replacement is REST-only.

## Promote — in-place lock without restart

`POST /workloads/{wid}/promote/` is the only way to transition a workload from "running a draft" to "running a locked production version" **without** a rolling restart:

- Artifact `status` flips draft → locked (becomes immutable).
- Workload's `artifactId` keeps pointing at the same artifact (now locked).
- Running pods are NOT restarted. Traffic uninterrupted.

If you also need a rolling *restart* to apply new env vars from a recent PATCH, do **not** reach for `POST /replacement/` with the same artifact ID — that 422s ("candidate artifact ID matches current artifact"). To restart the workload onto the same artifact's current spec, use `stop` → `start` (brief downtime). The intent split: promote = "the running version IS production"; replacement = "deploy a *different* artifact".

## PATCH on multi-container artifacts replaces the whole `containerGroups` array

If your artifact has multiple containers and you only want to change one, **fetch the full `spec` first, modify only the target container in place, and send the entire array back**. Sending one container will silently drop the others. The spec describes the schema shape but doesn't warn about this replacement-semantics gotcha.

Also: don't include `spec.type` in PATCH bodies — it's a read-only discriminator that the `UpdateArtifactRequest` write model rejects.

## Server-side image builds

If the artifact was created with `imageBuildConfig` referencing source code in DataRobot Files, the platform can build the image. Triggered with `POST /artifacts/{id}/builds/`; poll via `scripts/wait_for_build.py`. Two non-spec behaviors:

- On success, the platform **populates the artifact's `imageUri` automatically**. Re-`GET` the artifact to see it. Do **not** set `imageUri` by hand — a manual `PATCH` of it returns `422 {"detail": "Image URI '...' is not permitted on this cluster."}` (only build-produced images are allowed). If both `imageBuildConfig` and `imageUri` are supplied at create time, the build overwrites `imageUri` on completion.
- **Do not PATCH the artifact spec while a build is in progress.** A spec PATCH is a whole-spec read-modify-write, so it sends back the *pre-build* `imageUri` and clobbers the completion's auto-populate — the artifact keeps pointing at the **old** image and the next deploy silently runs stale code. Sequence spec edits (env/probes) *before* `build create`, or *after* `COMPLETED` with a fresh `GET` so the PATCH carries the new `imageUri`. After `COMPLETED`, confirm `imageUri` advanced before redeploying.
- Status sequence: `PENDING` → `IN_PROGRESS` → `BUILT` → `COMPLETED` (or → `FAILED`). **`BUILT` is intermediate** — image built locally but not yet pushed to the registry. Only `COMPLETED` is deployable; scheduling a workload on a `BUILT` artifact returns `422 runtime_image_uri ... None`. `wait_for_build.py` waits for `COMPLETED` specifically.
- Only drafts can build. Builds for locked artifacts can't be triggered or deleted.

## Rolling replacement — non-idempotent, 404-after-completion

- **Not idempotent.** Calling `POST /workloads/{id}/replacement/` while one is in progress queues a second swap. Always check via `GET /workloads/{id}/replacement/` (or `scripts/wait_for_replacement.py`) before retrying.
- **`GET /workloads/{id}/replacement/` returns 404** when no active replacement exists — body: `{"detail": "There is no active replacement for this workload."}`. Treat as "no replacement in progress", not as an error. The polling script handles this case explicitly.
- On `failed`, the workload reverts to the old artifact. Diagnose the candidate's pods via `diagnose_workload.py` before retrying.

## Replacement history

`GET /workloads/{id}/history/` returns the chronological list of past replacements — who, when, which strategy. Useful for audit ("which artifact version was running on 2026-04-15?") and rollback ("the previous artifact ID was X — replace back to that").
