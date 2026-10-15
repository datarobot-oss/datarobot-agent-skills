# Common error patterns

Failure mode points at the fix. This is the lookup table `diagnose_workload.py` uses internally; match symptoms here when drilling in manually.

## `CrashLoopBackOff`

```
state: waiting   reason: CrashLoopBackOff   restartCount: 5+
```

Container starts then exits non-zero. **Pull application logs** (`/otel/workload/{id}/logs/`) — app is throwing during startup. Common causes:

- Missing required env var
- Bad config (database URL, API key, …)
- Missing dependency in the image
- App listening on the wrong port (doesn't match the artifact's `port` field)
- Failed connection to a backing service (DB, cache, upstream API)

### Special case — `exec format error`

```
state: waiting   reason: CrashLoopBackOff
log line: exec format error
       (or: exec /entrypoint: no such file or directory  even though the file exists)
```

Wrong CPU architecture. DataRobot's worker nodes run **linux/amd64** only. An ARM64 image (default when building on Apple Silicon) crash-loops immediately. Fix:

```bash
docker buildx build --platform linux/amd64 -t <registry>/<image>:<tag> --push .
# Or multi-arch (Mac dev + DataRobot prod from one tag):
docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/<image>:<tag> --push .
```

Verify before referencing: `docker buildx imagetools inspect <registry>/<image>:<tag>` — `linux/amd64` must be present.

Then update the artifact's `imageUri` (PATCH for drafts; clone + PATCH + lock for locked) and roll out via `POST /workloads/{id}/replacement/`.

## `ImagePullBackOff` / `ErrImagePull`

```
state: waiting   reason: ImagePullBackOff
message: Failed to pull image "myregistry/myapp:v1": ...
```

- Wrong image URI (typo in tag or registry)
- Private registry without credentials configured
- Tag doesn't exist on the registry

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
- App slow to start — bump `initialDelaySeconds` (default 10s readiness, 30s liveness often too short for cold start)
- Health endpoint returns non-2xx — fix the app or point the probe at a working path

## Pending pod (`PodScheduled = False`)

```
phase: pending
condition: PodScheduled = False
```

K8s can't place the pod. Usually:

- Requested resources/bundle has no current cluster capacity
- Bundle ID invalid (typo, or removed from catalog) — re-run `GET /mlops/compute/bundles/`, pick a valid one

Try a smaller bundle or wait for capacity.

## Terminated with non-OOM reason

Check `exitCode` and `message`. Useful exit codes:

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

Exit codes >128: process killed by a signal (signal number = exit code − 128).

## Port not listening

Symptom: workload reaches `running`, but external requests time out, or readiness probe fails with `connection refused`.

Container started, but the app isn't listening on the artifact's `port`. Common causes:

- Image defaults to port 80 (nginx, httpd) but `port: 8000` is set. Fix via image env var (`PORT`, `LISTEN_PORT`) or `entrypoint` override.
- App binds to `127.0.0.1` instead of `0.0.0.0` (loopback only). Reconfigure the app.

Port 80 (and any port < 1024) is privileged on Linux. DataRobot runs containers as non-root, so privileged ports are rejected at the API — artifact spec must use port ≥ 1024.

## Image architecture mismatch

Covered above under `exec format error`. Signature:

- Build was on Apple Silicon (`uname -m` = `arm64`) without `--platform linux/amd64`
- Image manifest lacks `amd64` — `docker buildx imagetools inspect <ref>` shows only `arm64`

## `POST /workloads/` returns `422 runtime_image_uri ... None`

Build hasn't pushed the image to the registry yet — workload can't be scheduled.

Two causes (likeliest first):

1. **Build still `BUILT`, not `COMPLETED`** — the common case. `BUILT` = built locally, **not pushed to the registry yet**. Only `COMPLETED` is deployable. Sequence: `PENDING` → `IN_PROGRESS` → `BUILT` → `COMPLETED`. Gap between `BUILT` and `COMPLETED`: seconds to minutes for large images. Fix: wait for `COMPLETED` specifically (`scripts/wait_for_build.py` does this).
2. **Race condition (RAPTOR-17673)** — even after `COMPLETED`, the registry can briefly lag before the image resolves. Fix: wait a few seconds, retry the workload create. Platform-side fix in flight.

If build status is `FAILED`, workload create also 422s — but the fix is investigating the build, not retrying create. See the C2W reference's failure-modes section.

## Diagnostic decision tree

When the pattern isn't obvious:

1. **Is the container ever `running`?** Check `proton.statusDetails.replicas[].containers[].status`.
   - **Never `running`** → K8s/image-level issue. Check the container `reason` (`ImagePullBackOff`, `CrashLoopBackOff` with no log lines, etc.).
   - **Briefly `running` then died** → app-level issue. Pull `/otel/workload/{id}/logs/`.
2. **Is `restartCount > 0`?** `CrashLoopBackOff` — app keeps crashing after start. Always pull logs.
3. **Any condition `false`?** Find the first false condition, act on it (PodScheduled → scheduling; ContainersReady → probes/app; Ready → upstream of ContainersReady).
4. **No specific signal anywhere?** Pull the latest events — platform perspective often has the answer the runtime view doesn't.

If steps 1-4 don't yield a specific cause, the issue is in the application code — report logs to the user, don't guess.

## Web UI served through the endpoint behaves wrong

If the workload runs but a **browser-facing web app** served through
`dr workload endpoint <id>` misbehaves — 404s on assets/API, redirects to
the DataRobot login (`…?next=%2F`), `401 {"message":"Invalid API key"}` on
API calls, a login that never sticks, `403 "XSRF cookie does not match"`,
or a browser Basic-auth "Sign in" modal — the cause is the edge gateway,
not a crash. Key tell: **a failing request absent from `dr workload logs`
was rejected by the edge before reaching the container** (auth/`Authorization`
issue). See `references/web-uis-behind-the-edge.md` for the full
symptom→fix table; short version: make the app sub-path aware, disable
its own auth and CSRF, let the DataRobot edge authenticate.
