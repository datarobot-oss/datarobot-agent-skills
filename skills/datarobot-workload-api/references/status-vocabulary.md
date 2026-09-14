# Status vocabulary — agent action mapping

Enum values are documented in the OpenAPI spec — confirm exact values with `spec["components"]["schemas"]["WorkloadStatus"]` and similar. This file holds **only the agent-action mapping** for each value: what to *do* when a workload (or proton, container, replica) is in a given state. That mapping isn't in the spec.

## Workload status → next step

| Status | Next step |
|---|---|
| `submitted` | Wait. If stuck > 1 min, check `GET /workloads/{id}/events/` for scheduling issues |
| `provisioning` / `launching` | Wait. If stuck > 5 min, drill into `GET /workloads/{id}/protons/{pid}/statusDetails/` |
| `running` | Healthy — check telemetry if asked |
| `suspended` | Platform-paused — check events for the cause |
| `stopping` / `stopped` | If unintended, `POST /workloads/{id}/start/` |
| `errored` | Recoverable startup failure — run `scripts/diagnose_workload.py` and fix via section 1 (settings) or section 4 (artifact) |
| `terminated` | Unrecoverable — delete and recreate after fixing root cause |

Happy path: `submitted` → `provisioning` → `launching` → `running`. Only `running` and `stopped` are stable. There is no workload-level `updating` or `failed` status — a rolling redeploy is observed via the `candidate` proton's status, and terminal-failure matching should use `errored`/`terminated` only. `interrupted` is a proton-only status.

## Proton roles

A "proton" is one deployment instance (one artifact + one runtime config) on a workload.

- `active` — the currently-serving deployment. The default choice for diagnostics.
- `candidate` — only present during a rolling artifact replacement. If the replacement is what's failing, debug the `candidate`, not the `active`.

If no proton has the `active` role (rare, only during initial provisioning), pick the one with the most recent `createdAt`.

## Container / replica status → smoking gun

In `proton.statusDetails`, the per-pod detail. Read in this triage order:

1. **`replicas[*].containers[*].status` + `restartCount`** is the headline.
   - `waiting` + non-zero restarts → container can't start → pull logs.
   - `terminated` → ran and died → check `reason` (`OOMKilled`, exit code) → fix or pull logs.
2. **`replicas[*].conditions[*]`** — any condition with `value: false` is a smoking gun.
   - `PodScheduled: false` → scheduling failure (resources / bundle).
   - `ContainersReady: false` + `Ready: false` → probe failures or container not ready.
3. **`overallStatus.summary`** — DataRobot's human-readable interpretation. Useful for one-line user-facing diagnoses.

For symptom → fix mapping (CrashLoopBackOff, OOMKilled, etc.), see `references/common-error-patterns.md`.

## Build status

Sequence: `PENDING` → `IN_PROGRESS` → `BUILT` → `COMPLETED` (or → `FAILED` / `CANCELLED`). Lowercase variants (`pending` / `in-progress` / `completed` / `failed`) are also returned by some flows — normalize to uppercase before comparing.

- `PENDING` / `IN_PROGRESS` — keep polling.
- **`BUILT` — image built locally but NOT yet pushed to the registry. NOT deployable.** A workload scheduled on an artifact at `BUILT` returns `422 runtime_image_uri ... None`. Keep polling. The gap from `BUILT` to `COMPLETED` can be seconds to minutes for large images.
- `COMPLETED` — built AND pushed; only now is the image deployable.
- `FAILED` — terminal failure. Pull `/artifacts/{id}/builds/{bid}/logs/` for the cause.
- `CANCELLED` — terminal; the build was cancelled and will never complete. Treat like `FAILED`, not as still-in-progress.

The `wait_for_build.py` script enforces this: only `COMPLETED` exits success, `BUILT` keeps polling.

## Replacement status

- `submitted` / `initializing` / `staged` / `promoting` / `finalizing` / `canceling` — in progress, keep polling.
- `completed` — terminal success.
- `errored` / `cancelled` — terminal failure; workload reverted to old artifact. Diagnose the candidate before retrying. (There is no `failed` replacement status.)

The endpoint also returns **404** when no active replacement exists — that's "no replacement in progress", not an error. See `references/lifecycle-flows.md` for the full semantics.

## Importance levels — scheduling priority

`importance` controls scheduling priority and eviction behavior under cluster contention:

- `low` — dev, exploration, throwaway workloads. Most likely to be evicted/deprioritized.
- `moderate` — internal tools, non-critical services.
- `high` — production services.
- `critical` — production services that must not be evicted.

At scale (many replicas), use `high` or `critical` to reduce eviction risk.
