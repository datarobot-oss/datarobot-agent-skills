# Status vocabulary — agent action mapping

Enum values are in the OpenAPI spec — confirm exact values with `spec["components"]["schemas"]["WorkloadStatus"]` and similar. This file holds **only the agent-action mapping**: what to *do* in each state (workload, proton, container, replica). Not in the spec.

## Workload status → next step

| Status | Next step |
|---|---|
| `submitted` | Wait. Stuck > 1 min: check `GET /workloads/{id}/events/` for scheduling issues |
| `provisioning` / `launching` | Wait. Stuck > 5 min: drill into `GET /workloads/{id}/protons/{pid}/statusDetails/` |
| `running` | Healthy — check telemetry if asked |
| `updating` | Rolling redeploy in progress (settings change or artifact replacement); returns to `running` once the new replica passes readiness |
| `suspended` / `interrupted` | Platform-paused — check events for the cause |
| `stopping` / `stopped` | If unintended, `POST /workloads/{id}/start/` |
| `errored` | Recoverable startup failure — run `scripts/diagnose_workload.py`, fix via section 1 (settings) or section 4 (artifact) |
| `failed` / `terminated` | Unrecoverable — delete and recreate after fixing root cause |

Happy path: `submitted` → `provisioning` → `launching` → `running`. Only `running` and `stopped` are stable.

## Proton roles

A "proton" is one deployment instance (one artifact + one runtime config) on a workload.

- `active` — currently-serving deployment. Default choice for diagnostics.
- `candidate` — present only during a rolling artifact replacement. If the replacement is failing, debug the `candidate`, not `active`.

No `active` proton (rare, only during initial provisioning): pick the one with the most recent `createdAt`.

## Container / replica status → smoking gun

`proton.statusDetails`, per-pod detail. Triage order:

1. **`replicas[*].containers[*].status` + `restartCount`** — the headline.
   - `waiting` + non-zero restarts → container can't start → pull logs.
   - `terminated` → ran and died → check `reason` (`OOMKilled`, exit code) → fix or pull logs.
2. **`replicas[*].conditions[*]`** — any `value: false` is a smoking gun.
   - `PodScheduled: false` → scheduling failure (resources/bundle).
   - `ContainersReady: false` + `Ready: false` → probe failures or container not ready.
3. **`overallStatus.summary`** — DataRobot's human-readable interpretation. Good for one-line user-facing diagnoses.

Symptom → fix mapping (CrashLoopBackOff, OOMKilled, etc.): `references/common-error-patterns.md`.

## Build status

Sequence: `PENDING` → `IN_PROGRESS` → `BUILT` → `COMPLETED` (or → `FAILED`). Some flows return lowercase (`pending`/`in-progress`/`completed`/`failed`) — normalize to uppercase before comparing.

- `PENDING` / `IN_PROGRESS` — keep polling.
- **`BUILT` — built locally, NOT yet pushed to the registry. NOT deployable.** A workload scheduled on a `BUILT` artifact returns `422 runtime_image_uri ... None`. Keep polling. Gap from `BUILT` to `COMPLETED`: seconds to minutes for large images.
- `COMPLETED` — built AND pushed; only now deployable.
- `FAILED` — terminal failure. Pull `/artifacts/{id}/builds/{bid}/logs/` for the cause.

`wait_for_build.py` enforces this: only `COMPLETED` exits success, `BUILT` keeps polling.

## Replacement status

- `candidate-warming` / `switching` — in progress, keep polling.
- `completed` — terminal success.
- `failed` — terminal failure; workload reverted to old artifact. Diagnose the candidate before retrying.

The endpoint also returns **404** when no active replacement exists — "no replacement in progress," not an error. Full semantics: `references/lifecycle-flows.md`.

## Importance levels — scheduling priority

`importance` controls scheduling priority and eviction behavior under cluster contention:

- `low` — dev, exploration, throwaway workloads. Most likely to be evicted/deprioritized.
- `moderate` — internal tools, non-critical services.
- `high` — production services.
- `critical` — production services that must not be evicted.

At scale (many replicas), use `high` or `critical` to reduce eviction risk.
