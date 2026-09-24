# Artifact lifecycle — rules the spec doesn't state

SKILL.md section 4 has the operational summary and example code. This reference holds **only the behavioral rules** not visible from the spec alone (`POST /artifacts/`, `PATCH /artifacts/{id}/`, etc. shapes are in the spec).

## Lifecycle states and transitions

```
create  →  iterate (PATCH while draft)  →  lock  →  rolling replacement
              ↳ status=draft                ↳ status=locked, immutable
                                              clones create new drafts
```

- Artifacts start `draft` on create.
- `draft`: PATCH applies in place.
- `locked`: immutable. Any edit needs `POST /artifacts/{id}/clone/` (new draft, same artifact repository), then PATCH the clone.
- Locked, to deploy changes: trigger a **rolling replacement** on the workload (`POST /workloads/{wid}/replacement/`). Promote is the alternative for the in-place draft→locked case.

## Replacement preconditions — and the draft same-artifact exception

`POST /workloads/{id}/replacement/` enforces two preconditions the spec doesn't spell out:

1. **Status must match.** **HTTP 400** `{"detail": "Artifact status mismatch: ..."}` unless the candidate's status matches the running artifact's (draft↔draft, locked↔locked).
2. **Same-artifact rule — drafts exempt.** Passing the *current* `artifactId` returns **HTTP 422** `{"detail": ["Cannot replace with the same artifact — candidate artifact ID matches current artifact."]}` for **locked** artifacts. **Drafts are exempt** — same-artifact replacement is allowed on a draft, so the C2W rebuild-then-replace loop works.

Neither rule is in the spec's path docs. No `dr workload replacement` CLI subcommand — replacement is REST-only.

### Applying a change to the SAME draft a workload runs

`code sync` + `build create` (or a spec PATCH) keep the same artifact ID; a running workload does **not** auto-adopt the change — trigger a redeploy. Options, all rolling (zero-downtime at `replicaCount`/`minCount` ≥ 2; a single replica has a brief gap):

| Goal | Do this |
|---|---|
| roll onto the latest build / spec (works on **any** cluster version) | `PATCH /workloads/{id}/settings/` — re-send the runtime body (same shape `GET /workloads/{id}/settings/` returns; even unchanged values trigger the roll). Re-reads the artifact's current spec + latest `COMPLETED` build's `imageUri`. Returns `202`. |
| same, but explicit warmup / rollback-window control | `POST /replacement/` onto the same draft |
| lock the running draft in place | `POST /workloads/{id}/promote/` (no restart) |
| switch to a different / newly-locked artifact | `POST /replacement/` onto the other artifact ID |
| locked → new content | clone → patch the draft → lock the new draft → `POST /replacement/` onto the clone |

## Promote — in-place lock without restart

`POST /workloads/{wid}/promote/` is the only way to move a workload from "running a draft" to "running a locked production version" **without** a rolling restart:

- Artifact `status` flips draft → locked (becomes immutable).
- Workload's `artifactId` keeps pointing at the same artifact (now locked).
- Running pods are NOT restarted. Traffic uninterrupted.

For a rolling *restart* to apply new env vars from a recent PATCH: roll the workload onto the draft's current spec with `PATCH /workloads/{wid}/settings/` (re-send the runtime body — even unchanged, triggers the rolling redeploy). Same-artifact `POST /replacement/` also works for drafts. Intent split: promote = "the running version IS production"; replacement = "deploy a *different* artifact" (or the same draft); settings-PATCH = "restart onto the same artifact's latest spec/build".

## PATCH on multi-container artifacts replaces the whole `containerGroups` array

Changing one container in a multi-container artifact: **fetch the full `spec` first, modify only the target container in place, send the entire array back.** Sending one container silently drops the others. The spec describes the schema shape but doesn't warn about this replacement-semantics gotcha.

Also: don't include `spec.type` in PATCH bodies — a read-only discriminator the `UpdateArtifactRequest` write model rejects.

## Server-side image builds

If the artifact was created with `imageBuildConfig` referencing source in DataRobot Files, the platform can build the image. Trigger: `POST /artifacts/{id}/builds/`; poll via `scripts/wait_for_build.py`. Two non-spec behaviors:

- On success, the platform **populates `imageUri` automatically**. Re-`GET` to see it. Do **not** set `imageUri` by hand — a manual `PATCH` returns `422 {"detail": "Image URI '...' is not permitted on this cluster."}` (only build-produced images allowed). If both `imageBuildConfig` and `imageUri` are supplied at create time, the build overwrites `imageUri` on completion.
- **Do not PATCH the artifact spec while a build is in progress.** A spec PATCH is a whole-spec read-modify-write, so it sends back the *pre-build* `imageUri` and clobbers the completion's auto-populate — artifact keeps pointing at the **old** image, next deploy silently runs stale code. Sequence spec edits (env/probes) *before* `build create`, or *after* `COMPLETED` with a fresh `GET` so the PATCH carries the new `imageUri`. After `COMPLETED`, confirm `imageUri` advanced before redeploying.
- Status: `PENDING` → `IN_PROGRESS` → `BUILT` → `COMPLETED` (or → `FAILED`). **`BUILT` is intermediate** — built locally, not yet pushed. Only `COMPLETED` is deployable; scheduling on a `BUILT` artifact returns `422 runtime_image_uri ... None`. `wait_for_build.py` waits for `COMPLETED` specifically.
- Only drafts build. Builds for locked artifacts can't be triggered or deleted.

## Watching a rolling roll — track the active proton's id, not the proton count

Both a settings-PATCH roll and a replacement leave the **old proton in
`GET /workloads/{id}/protons/` as `status: stopped` with no `role`** for some
time after the new one goes active — the list doesn't shrink to one entry
right away. A watcher waiting for "exactly one proton" will hang. For a
replacement, `scripts/wait_for_replacement.py` sidesteps this by polling
`GET /workloads/{id}/replacement/`'s own `status` field (treating its 404
as settled) rather than counting protons — use it as-is. A settings-PATCH
roll has no equivalent status endpoint and no bundled script — a custom
watcher should poll `GET /workloads/{id}/protons/` and watch for the
**active proton's id to change** to the new candidate's id (`role:
"active"`), not for the list to shrink to one entry.

## Rolling replacement — non-idempotent, 404-after-completion

- **Not idempotent.** Calling `POST /workloads/{id}/replacement/` while one is in progress queues a second swap. Check via `GET /workloads/{id}/replacement/` (or `scripts/wait_for_replacement.py`) before retrying.
- **`GET /workloads/{id}/replacement/` returns 404** when no active replacement exists — body: `{"detail": "There is no active replacement for this workload."}`. Treat as "none in progress", not an error. The polling script handles this explicitly.
- On `failed`, the workload reverts to the old artifact. Diagnose the candidate's pods via `diagnose_workload.py` before retrying.

## Replacement history

`GET /workloads/{id}/history/` returns the chronological list of past replacements — who, when, which strategy. Useful for audit ("which artifact version was running on 2026-04-15?") and rollback ("previous artifact ID was X — replace back to that").
