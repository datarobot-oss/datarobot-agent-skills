---
name: datarobot-workload-api
description: >-
  Use when the user wants to create, configure, scale, debug, observe, or roll
  out container workloads on DataRobot's Workload API. Triggers: deploy a
  container as a managed service; list/start/stop workloads; change replica
  counts or autoscaling; pick CPU/GPU compute bundles; inject DataRobot
  credentials as env vars; diagnose stuck/errored/crash-looping workloads
  (CrashLoopBackOff, ImagePullBackOff, OOMKilled, probe failures, exec format
  error); pull application logs/OpenTelemetry traces/metrics/request stats;
  create or iterate container artifacts; build images server-side; lock
  artifacts for production; zero-downtime rolling artifact replacement.
---

# DataRobot Workload API

Runs containers as managed, autoscalable DataRobot services. Four jobs — pick by intent:

1. **Create / configure / scale** — deploy a container; change replicas, resources, autoscaling, bundle; inject credentials
2. **Diagnose** — workload stuck, errored, or crash-looping
3. **Observe** — logs, traces, metrics, service stats for a running workload
4. **Artifact lifecycle** — iterate drafts, build images, lock for production, roll out new versions

## Prerequisites

Auth: like `gh`. `dr auth login` (or existing `.env`/`~/.config/datarobot/drconfig.yaml`) persists credentials — no per-run env vars needed. Verify with `dr auth check`. On failure, run `datarobot-setup`.

**Keep the CLI current** (like `datarobot-agent-assist`): `dr self update --force`. Never gate on a pinned version. If a subcommand still errors `unknown command` after update (seen with `config`/`up` — `references/declarative-cli-deploy.md`), use the raw-REST fallback below.

`DATAROBOT_ENDPOINT` (must end `/api/v2`) and `DATAROBOT_API_TOKEN`: required as env vars only for raw REST (`scripts/`, `httpx`/`curl`) or CI — these bypass CLI auth. Header: `Authorization: Bearer ${DATAROBOT_API_TOKEN}`. Not in the `datarobot` Python SDK — call REST directly.

**Transport:** examples use Python `httpx` (`pip install httpx`); `curl` or the `pulumi-datarobot` provider work too.

## Bundled scripts

Python in `scripts/`. Each uses `httpx`, reads `DATAROBOT_ENDPOINT` + `DATAROBOT_API_TOKEN`:

- `wait_for_running.py <workload_id>` — poll until `running`; exit 2 on terminal failure, 3 on timeout
- `diagnose_workload.py <workload_id>` — run the 5-step debug flow, print a diagnosis (`--json` for machine output)
- `wait_for_build.py <artifact_id> <build_id>` — poll a server-side image build; dumps last 2KB of logs on `FAILED`
- `wait_for_replacement.py <workload_id>` — poll a rolling replacement; handles the 404-when-cleared case
- `check_limits.py` — print effective org scaling limits via `/account/info/`

## Deeper docs in references/

In `references/`:

- `status-vocabulary.md` — status enums and transitions
- `common-error-patterns.md` — CrashLoopBackOff / ImagePullBackOff / OOMKilled / probe / exec-format
- `schema-reference.md` — schemas, credential-type→key maps, spec quirks
- `lifecycle-flows.md` — draft→lock→prod rules, replacement preconditions, redeploy matrix
- `code-to-workload.md` — deploy from source: `dr` CLI, `codeRef`, Execution Environments
- `declarative-cli-deploy.md` — `dr workload config`/`up`: one-command create/build/deploy
- `web-uis-behind-the-edge.md` — web UI through the endpoint: prefix, auth gate, CSRF, WebSockets

## OpenAPI spec is source of truth

At `${DATAROBOT_ENDPOINT}/openapi.yaml` (some instances omit Workload API paths — see `references/schema-reference.md`). **~5 MB — never dump whole.** Save once, slice with `yq` (or `print()` one key in Python):

```bash
curl -sS "${DATAROBOT_ENDPOINT}/openapi.yaml" -o /tmp/wapi-spec.yaml
yq '.components.schemas.CreateWorkloadRequest' /tmp/wapi-spec.yaml
```

Workload paths key with `/api/v2/` — see `references/schema-reference.md`.

---

# 1. Create / configure / scale

## Deploy a container (common case)

```yaml
# spec.yaml — JSON also accepted; spec is sent verbatim
name: my-api-service
importance: low
artifact:
  name: my-api-service-artifact
  spec:
    type: service
    containerGroups:
      - name: default
        containers:
          - name: main
            imageUri: ghcr.io/org/my-app:latest
            port: 8000
            primary: true
            readinessProbe: {path: /readyz, port: 8000, initialDelaySeconds: 10}
            livenessProbe: {path: /healthz, port: 8000, initialDelaySeconds: 30}
runtime:
  containerGroups:
    - name: default          # must match artifact.spec.containerGroups[].name (above)
      replicaCount: 1
      containers:
        - name: main
          resourceAllocation: {cpu: 1, memory: "512MB"}
```

```bash
dr workload create --spec-file spec.yaml         # 4xx: 400=schema/limit, 403=cap (run check_limits.py), 409=name conflict
dr workload get <workload_id>                    # or `dr workload status` — poll until status=running
```

Lifecycle one-liners: `dr workload {stop|start|delete|endpoint|list} <id>`.

Raw fallback when CLI unavailable: `httpx.post(f"{base}/workloads/", headers=headers, json=spec)` + `r.raise_for_status()` + `r.json()["id"]`; poll with `python scripts/wait_for_running.py <workload_id>`.

**Critical gotchas:**

- `importance`: `low`/`moderate`/`high`/`critical`. `type`: `service` (default) or `nim`. One container per group must be `primary: true`.
- `cpu`: cores (float OK). `memory`: decimal string (`"512MB"`, units B/KB/MB/GB) or byte integer. No Kubernetes binary suffixes (`Mi`/`Gi`).
- `port` must be `>= 1024`. Container must actually listen on it (image env var or entrypoint).
- Image needs a **linux/amd64** manifest. Apple Silicon defaults to ARM64: crash-loops with `exec format error`. Build: `docker buildx build --platform linux/amd64,linux/arm64 -t <ref> --push .`.
- Status: `submitted` → `provisioning` → `launching` → `running` (happy path); `updating` = rolling redeploy; `errored` recoverable; `failed`/`terminated` unrecoverable. Full table: `references/status-vocabulary.md`.

## Web UI through the endpoint

Browser web app (UI + backend/API/WebSocket) via `dr workload endpoint <id>`, not headless: edge gateway serves it under a path prefix. **Strips prefix inbound** (no outbound rewrite; app must be sub-path aware). **Is the auth gate** (DataRobot login), **hijacks `Authorization`** (→ `401 {"message":"Invalid API key"}`, container never sees it). **Passes WebSockets through**. Pattern: base-path = prefix (from `WORKLOAD_ID`) + inbound shim, CSRF off, unauthenticated probe path. Disable app auth only with user sign-off. Detail: `references/web-uis-behind-the-edge.md`.

## Update paths

| User intent | Endpoint | Effect |
|---|---|---|
| Rename / redescribe / change importance | `PATCH /workloads/{id}/` | Metadata only — no restart |
| Change replicas / resources / autoscaling on the same artifact | `PATCH /workloads/{id}/settings/` | Triggers rolling redeploy |
| Deploy a different artifact (new image / version) | `POST /workloads/{id}/replacement/` | Rolling swap — see section 4 |

## Replicas, resources, autoscaling

`PATCH /workloads/{wid}/settings/`, full body. Use `replicaCount` OR `autoscaling`, not both. Read via `GET /workloads/{wid}/settings/` first, then PATCH back:

```python
httpx.patch(
    f"{base}/workloads/{wid}/settings/",
    headers=headers,
    json={
        "runtime": {
            "containerGroups": [
                {
                    "name": "default",
                    "replicaCount": 3,
                    "containers": [
                        {
                            "name": "main",
                            "resourceAllocation": {"cpu": 2, "memory": "1GB"},
                        }
                    ],
                    # OR: "autoscaling": {"enabled": True, "policies": [{
                    #       "scalingMetric": "cpuAverageUtilization",
                    #       "target": 70, "minCount": 1, "maxCount": 10}]}
                }
            ]
        }
    },
)
```

`scalingMetric` values: `cpuAverageUtilization`, `httpRequestsConcurrency`, `gpuCacheUtilization`, `gpuRequestQueueDepth`, or a custom NIM metric. Settings updates are **rolling** — zero-downtime needs `replicaCount >= 2` (or autoscaling `minCount >= 2`).

## Org-set scaling limits

Admin-set caps: `maxConcurrentWorkloads`, `maxWorkloadReplicas`. `0` = unlimited; users can't change them. Read via **`GET /account/info/`** → `{"limits": {"maxConcurrentWorkloads": N, "maxWorkloadReplicas": M}}` (or `python scripts/check_limits.py`). `/users/{uid}/` and `/organizations/{id}/` need Admin API access. Over limit: **HTTP 403** `{"detail": "Requested replicas (N) exceeds the maximum allowed (M)."}` — check limits first; propose the max, or flag admin help needed.

## GPU/VRAM via compute bundle

`resourceAllocation` accepts only `cpu`, `memory`, `gpu` (count) — no `gpuType`/`gpuMemory` field. For a GPU model/VRAM size: `GET /mlops/compute/bundles/` lists bundles (`cpu.small`, `gpu.l4.small`, `gpu.a10g.medium`); pass `"resourceBundles": ["gpu.l4.small"]` (a list, but only ONE bundle allowed) under the container group. A set bundle overrides `resourceAllocation` cpu/memory.

## Credential injection — no hardcoded secrets

DataRobot stores credentials centrally, injects into `environmentVars` by reference:

```python
"environmentVars": [
    {"name": "PLAIN_VAR", "value": "literal-value"},
    {"source": "dr-credential", "name": "AWS_ACCESS_KEY_ID",
     "drCredentialId": "<credential-id>", "key": "awsAccessKeyId"},
]
```

Flow: `GET /credentials/?limit=50` → note `credentialType` → look up valid `key` names in `references/schema-reference.md`.

## Create from artifact

Provide `artifactId` instead of an inline `artifact` block. `runtime`'s `containerGroups[].name`/`containers[].name` must match the artifact's.

---

# 2. Diagnose

## Full diagnosis, one command

```bash
python scripts/diagnose_workload.py <workload_id>
```

Runs the 5 steps below, prints a report (status, logTail signals, flagged events, proton K8s detail, evidence, recommended fix, console URL). `--json` for machine output. Empty `Evidence`: pull application logs via section 3 — don't guess from status alone.

## The 5-step flow

Script does this; steps below for ambiguous output or one-off calls.

1. **`GET /workloads/{id}/`** — `status`, `statusDetails.logTail` (~30 lines; scan for `error`/`exception`/`traceback`/`killed`/`permission denied`/`connection refused`), `statusDetails.conditions`. `statusDetails` is `null` during `submitted`/`provisioning` — guard for it.
2. **`GET /workloads/{id}/events/`** — flag `type: Warning` or `reason` with `Failed`/`Error`/`Kill`/`OOM`; the last Warning before `errored` is usually the trigger.
3. **`GET /workloads/{id}/protons/`** — pick `role: "active"` (or the `candidate` during a rolling replacement; else newest `createdAt`).
4. **`GET /workloads/{id}/protons/{pid}/statusDetails/`** — `204` while initializing (not an error). Read `replicas[*].containers[*].status`+`restartCount` → `replicas[*].conditions[*]` (any `value:false`) → `overallStatus.summary`.
5. **Application logs** — section 3.

Common patterns (`CrashLoopBackOff`, `ImagePullBackOff`, `OOMKilled`, probe/pending, `exec format error`) and fixes: `references/common-error-patterns.md`.

## Diagnosis output

```
Workload {id} — Diagnosis
- Status: {current}
- Root cause: {one sentence}
- Evidence: {the specific logTail line, condition, container reason, or event}
- Recommended fix: {next step — section 1 (settings), section 4 (artifact), or app code}
- Console: https://app.datarobot.com/console-nextgen/workloads/{id}/overview
```

---

# 3. Observe

| Stream | Endpoint | Needs app instrumentation? |
|---|---|---|
| Logs | `/otel/workload/{id}/logs/` | No — auto from stdout/stderr |
| Traces | `/otel/workload/{id}/traces/` | **Yes** (OTEL spans) |
| Metrics | `/otel/workload/{id}/metrics/autocollectedValues/` | Partially |
| Service stats | `/workloads/{id}/stats/` | No — DataRobot edge proxy |
| Replacement history | `/workloads/{id}/history/` | No — platform |
| Lifecycle events | `/workloads/{id}/events/` | No — platform |

Check `r.status_code` before `.json()`: 401 bad token, 404 not found, 429 rate-limited (exponential backoff). List endpoints accept `limit` + `offset`.

## Logs

```bash
dr workload logs <wid> --level error --limit 100   # --follow streams; --output-format json
```

`--level` is a MINIMUM severity threshold, not an exact match. For substring filtering on the message body, or proton-scoped logs (proton IDs: section 2), drop to REST — `dr workload logs` lacks these filters:

```python
r = httpx.get(
    f"{base}/otel/workload/{wid}/logs/",
    headers=headers,
    params=[
        ("searchKeys", "proton_id"),
        ("searchValues", pid),
        ("searchKeys", "level"),
        ("searchValues", "error"),
    ],
)
```

`searchKeys`/`searchValues` are positional parallel lists — pass a **list of tuples** to httpx (dict can't repeat keys). `includes=<substring>`: case-sensitive substring filter on the message body.

## Traces

```python
traces = httpx.get(f"{base}/otel/workload/{wid}/traces/", headers=headers).json()[
    "data"
]
# summary: traceId, rootSpanName, rootServiceName, duration (NANOSECONDS), spansCount, errorSpansCount
trace_id = next(
    (t["traceId"] for t in traces if t.get("errorSpansCount", 0) > 0),
    traces[0]["traceId"],
)
trace = httpx.get(
    f"{base}/otel/workload/{wid}/traces/{trace_id}/", headers=headers
).json()
```

> **`duration` is NANOSECONDS**, summaries and spans. Divide by 1,000,000 for ms before display. Empty `data`: app not instrumented — tell the user to wire up OTEL.

## Metrics + service stats

Convert before display: `bytes`→MB (`/1024**2`), `nanocores`→cores (`/1_000_000`), `percentage` already %.

```python
stats = httpx.get(f"{base}/workloads/{wid}/stats/", headers=headers).json()
# {"period": {...}, "metrics": {totalRequests, serverErrors, userErrors, slowRequests,
#   responseTime, requestsPerMinute, concurrentRequests, *ErrorRate}}. /workloads/stats/ = aggregate.
```

> **Destructive:** `DELETE /workloads/{id}/stats/?metricName=<name>` zeroes a metric's history — only on explicit request.

## Output format

Logs: `timestamp | level | message`, ERROR/CRITICAL first. Traces: table sorted by errors desc then recency. Metrics: apply unit conversion before display. Service stats one-liner: *"`{totalRequests}` requests, `{totalErrorRate*100:.2f}%` errors, `{responseTime:.1f}` ms avg, `{requestsPerMinute}` req/min."* Empty data: state *why* (not running, not instrumented, empty window) — not just "no data".

---

# 4. Artifact lifecycle

**Artifact**: immutable-after-lock definition of what a workload runs (image, port, env vars, probes). **Workload**: the running instance + its runtime (replicas, resources, autoscaling). Resources do NOT belong on the artifact.

## Choose a redeploy path

Find the running artifact (`workload["artifactId"]`), check `artifact["status"]`. A running workload does **not** auto-adopt a rebuild — redeploy is required.

- **Same draft (C2W loop) — in-place edit or rebuild.** PATCH/rebuild the draft, roll with `PATCH /workloads/{id}/settings/`: re-send the runtime body (even unchanged — triggers rolling `202`, re-reads current spec + latest `COMPLETED` build). Zero-downtime at ≥2 replicas. (`POST /replacement/` onto the same draft also works.)
- **Different / locked artifact.** `POST /replacement/` onto the other artifact ID. Locked in-place edit: clone → PATCH clone → lock → replace onto the clone.

**Lock:** `dr artifact lock <id>` (= `PATCH /artifacts/{id}/ {"status":"locked"}`). **Promote** (`POST /workloads/{wid}/promote/`, 200) locks the running draft in place, no restart. Runtime-only changes (replicas/resources/autoscaling) → `PATCH /settings/`; a PATCH to the artifact affects live workloads only on redeploy.

Preconditions (status-match, same-artifact rule) and the full redeploy matrix: `references/lifecycle-flows.md`.

## Image source

The artifact's `imageUri` must point at a registry DataRobot can pull from (image-pull creds not yet accepted at workload creation). Two paths:

1. **Bring your own image** — public registry or one the admin pre-configured. `docker buildx ... --platform linux/amd64`, push, set `imageUri`. Default flow.
2. **Code-to-Workload (C2W)** — no local Docker / no public registry: `dr artifact code init` + `sync`, then `dr artifact build create` builds server-side, pushes to DataRobot's internal registry, and populates `imageUri`. Full flow: `references/code-to-workload.md`.

Poll: `python scripts/wait_for_build.py <artifact_id> <build_id>`; only drafts build. **`imageUri` is build-managed** — never hand-PATCH it (`422` "not permitted on this cluster"), never PATCH the spec *mid-build* (whole-spec write clobbers the pending image → redeploys the old one). Edit spec before `build create` or after `COMPLETED`.

> **C2W may still need `ENABLE_WORKLOAD_API_CONTAINERS=true`** (org-set; not re-verified this session).

## Rolling artifact replacement

```python
httpx.post(
    f"{base}/workloads/{wid}/replacement/",
    headers=headers,
    json={
        "artifactId": new_artifact_id,
        "strategy": "rolling",  # only "rolling" supported
        "config": {"warmupDurationMinutes": 2, "keepOldVersionMinutes": 5},  # optional
        # "runtime": {...}  # optional; same shape as PATCH /settings/
    },
)
```

Monitor: `python scripts/wait_for_replacement.py <workload_id>`. Preconditions: status must match (draft↔draft/locked↔locked, else `400`); same-artifact replacement 422s for locked, works for drafts — for a draft roll without replacement, use `PATCH /settings/`. **Not idempotent** — a second `POST` queues another swap. `GET .../replacement/` `404` = none in progress. `DELETE` to cancel. Detail: `references/lifecycle-flows.md`.

---

## Related skills

- `datarobot-setup` — install SDK, configure auth, set env vars
- `datarobot-app-framework-cicd` — declarative artifact + workload management via Pulumi and CI/CD
- `datarobot-external-agent-monitoring` — instrument arbitrary agent code with OTEL → DataRobot
