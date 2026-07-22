# Common error patterns

When a workload fails, the specific failure mode points at the fix. This is the lookup table the `diagnose_workload.py` script uses internally; agents that drill in manually should match symptoms here.

## `CrashLoopBackOff`

```
state: waiting   reason: CrashLoopBackOff   restartCount: 5+
```

The container starts then exits non-zero. **Pull application logs** (`/otel/workload/{id}/logs/`) — the app is throwing during startup. Common causes:

- Missing required env var
- Bad config (database URL, API key, …)
- Missing dependency in the image
- App listening on the wrong port (port doesn't match the artifact's `port` field)
- Failed connection to a backing service (DB, cache, upstream API)

### Special case — `exec format error`

```
state: waiting   reason: CrashLoopBackOff
log line: exec format error
       (or: exec /entrypoint: no such file or directory  even though the file exists)
```

The image is the wrong CPU architecture. DataRobot's worker nodes run **linux/amd64** only. An ARM64 image (the default when you `docker build` on Apple Silicon) crash-loops immediately. Fix:

```bash
docker buildx build --platform linux/amd64 -t <registry>/<image>:<tag> --push .
# Or multi-arch (Mac dev + DataRobot prod from one tag):
docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/<image>:<tag> --push .
```

Verify before referencing: `docker buildx imagetools inspect <registry>/<image>:<tag>` — `linux/amd64` must be present in the manifest.

Then update the artifact's `imageUri` (PATCH for drafts; clone + PATCH + lock for locked artifacts) and roll out via `POST /workloads/{id}/replacement/`.

## `ImagePullBackOff` / `ErrImagePull`

```
state: waiting   reason: ImagePullBackOff
message: Failed to pull image "myregistry/myapp:v1": ...
```

- Wrong image URI (typo in tag or registry)
- Private registry without credentials configured
- Tag that doesn't exist on the registry

Verify the image is pullable from a fresh machine outside DataRobot before referencing it. Check tag spelling.

## `OOMKilled`

```
state: terminated   reason: OOMKilled   exitCode: 137
```

Container exceeded its memory limit. Bump `memory` in `runtime.containerGroups[0].containers[0].resourceAllocation` via `PATCH /workloads/{id}/settings/`, or pick a larger compute bundle.

## Probe failures (`ContainersReady = False`)

```
condition: ContainersReady = False
reason: ReadinessProbe failed
```

- Probe path/port doesn't match what the app actually exposes
- App is slow to start — bump `initialDelaySeconds` on the probe (default 10s for readiness, 30s for liveness is often not enough for cold-start)
- App's health endpoint returns non-2xx — fix the app or point the probe at a working path

## Pending pod (`PodScheduled = False`)

```
phase: pending
condition: PodScheduled = False
```

K8s can't place the pod. Usually:

- Requested resources/bundle has no current capacity on the cluster
- The bundle ID is invalid (typo, or removed from the catalog) — re-run `GET /mlops/compute/bundles/` and pick a valid one

Try a smaller bundle or wait for capacity.

## Terminated with non-OOM reason

Look at `exitCode` and `message`. Useful exit codes:

| Exit code | Likely cause |
|---|---|
| `0` | Clean exit (rare for services) |
| `1` | Generic app error |
| `2` | Misuse of shell builtins / argparse |
| `126` | Command found but not executable |
| `127` | Command not found |
| `137` | SIGKILL (often `OOMKilled` — confirm with `reason`) |
| `139` | Segfault |
| `143` | SIGTERM (graceful shutdown signal received) |

Exit codes >128 indicate the process was killed by a signal (signal number = exit code − 128).

## Port not listening

Symptom: workload reaches `running` but external requests time out, or readiness probe fails with `connection refused`.

The container started, but the app inside isn't listening on the `port` you set in the artifact. Common causes:

- Image defaults to port 80 (nginx, httpd) but you set `port: 8000`. Fix by configuring the image via env var (`PORT`, `LISTEN_PORT`) or by overriding `entrypoint`.
- App is binding to `127.0.0.1` instead of `0.0.0.0` (only accepts loopback connections). Reconfigure the app.

Port 80 (and any port < 1024) is privileged on Linux. DataRobot runs containers as non-root, so privileged ports are rejected at the API level — the artifact spec must use port ≥ 1024.

## Image architecture mismatch

Covered above under `exec format error`. The signature is:

- Build was on Apple Silicon (`uname -m` = `arm64`) without `--platform linux/amd64`
- Image manifest lacks an `amd64` entry — `docker buildx imagetools inspect <ref>` shows only `arm64`

## `POST /workloads/` returns `422 runtime_image_uri ... None`

The build hasn't pushed the image to the registry yet, so the workload can't be scheduled.

Two causes (in order of likelihood):

1. **The build is still `BUILT`, not `COMPLETED`** — the most common case. `BUILT` means the image was built locally on the build host but **has NOT been pushed to the registry yet**. `COMPLETED` is the only state where the image is deployable. Sequence: `PENDING` → `IN_PROGRESS` → `BUILT` → `COMPLETED`. The gap between `BUILT` and `COMPLETED` can be seconds to minutes for large images. Fix: wait for `COMPLETED` specifically (`scripts/wait_for_build.py` does this).
2. **Race condition (RAPTOR-17673)** — even after `COMPLETED`, the registry can briefly lag and the image isn't yet resolvable. Fix: wait a few seconds and retry the workload create. Platform-side fix in flight.

If the build status is `FAILED`, the workload create will also 422 — but in that case the fix is to investigate the build, not retry the workload create. See the C2W reference's failure-modes section.

## Diagnostic decision tree

When you don't know which pattern applies:

1. **Is the container ever `running`?** Check `proton.statusDetails.replicas[].containers[].status`.
   - **Never `running`** → it's a K8s / image-level issue. Check the container `reason` (`ImagePullBackOff`, `CrashLoopBackOff` with no log lines, etc.).
   - **Briefly `running` then died** → it's an app-level issue. Pull `/otel/workload/{id}/logs/`.
2. **Is `restartCount > 0`?** That's `CrashLoopBackOff` — the app keeps crashing after start. Always pull logs.
3. **Are any conditions `false`?** Find the first false condition and act on it (PodScheduled → scheduling; ContainersReady → probes/app; Ready → ContainersReady is upstream).
4. **No specific signal anywhere?** Pull the latest events — the platform's perspective often has the answer the runtime view doesn't.

If steps 1-4 don't yield a specific cause, the issue is in the application code — report logs to the user, don't guess.

## Web UI served through the endpoint behaves wrong

If the workload runs but a **browser-facing web app** served through
`dr workload endpoint <id>` misbehaves — 404s on assets/API, redirects to the
DataRobot login (`…?next=%2F`), `401 {"message":"Invalid API key"}` on API
calls, a login that never sticks, `403 "XSRF cookie does not match"`, or a
browser Basic-auth "Sign in" modal — the cause is the edge gateway, not a crash.
Key tell: **a failing request that does NOT appear in `dr workload logs` was
rejected by the edge before reaching the container** (auth/`Authorization`
issue). See `references/web-uis-behind-the-edge.md` for the full symptom→fix
table; the short version is: make the app sub-path aware, disable the app's own
auth and CSRF, and let the DataRobot edge authenticate.
