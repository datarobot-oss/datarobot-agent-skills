---
name: datarobot-workload-api
description: >-
  Use when the user wants to create, configure, scale, debug, observe, or roll
  out container workloads on DataRobot's Workload API. Triggers include:
  deploying a container as a managed service, listing/starting/stopping
  workloads, changing replica counts or autoscaling, picking CPU/GPU compute
  bundles, injecting DataRobot credentials as env vars, diagnosing workloads
  that are stuck / errored / crash-looping (CrashLoopBackOff, ImagePullBackOff,
  OOMKilled, probe failures, exec format error), pulling application logs /
  OpenTelemetry traces / metrics / request stats, creating or iterating
  container artifacts, building images server-side, locking artifacts for
  production, or doing a zero-downtime rolling artifact replacement.
---

# DataRobot Workload API

Run container images as managed, autoscalable services on DataRobot. One skill, four jobs — pick the section by user intent:

1. **Create / configure / scale** — deploy a container; change replicas, resources, autoscaling, bundle; inject credentials
2. **Diagnose** — workload is stuck, errored, or crash-looping
3. **Observe** — logs, traces, metrics, service stats for a running workload
4. **Artifact lifecycle** — iterate drafts, build images, lock for production, roll out new versions

## Prerequisites

`DATAROBOT_ENDPOINT` (must end in `/api/v2`) and `DATAROBOT_API_TOKEN` must be set. Run `datarobot-setup` if not. Auth header: `Authorization: Bearer ${DATAROBOT_API_TOKEN}`. The Workload API is not in the `datarobot` Python SDK — call REST directly.

**Transport.** Examples use Python `httpx` (`pip install httpx`). The API is plain HTTP, so equivalent calls work via `curl` or the `pulumi-datarobot` Pulumi provider declaratively. The skill teaches the model; transport is interchangeable.

## Bundled scripts

Runnable Python in `scripts/` (this skill's folder). Each uses `httpx` and reads `DATAROBOT_ENDPOINT` + `DATAROBOT_API_TOKEN`:

- `wait_for_running.py <workload_id>` — poll until `running`; exit 2 on terminal failure, 3 on timeout
- `diagnose_workload.py <workload_id>` — run the 5-step debug flow, print a structured diagnosis (`--json` for machine-readable)
- `wait_for_build.py <artifact_id> <build_id>` — poll a server-side image build; dumps last 2KB of logs on `FAILED`
- `wait_for_replacement.py <workload_id>` — poll a rolling replacement; handles the 404-when-cleared case
- `check_limits.py` — print the user's effective org-set scaling limits via `/account/info/`

## Deeper docs in references/

The SKILL.md is the operational core. Detail an agent needs occasionally lives in `references/`:

- `references/status-vocabulary.md` — workload + proton status enums and lifecycle transitions
- `references/common-error-patterns.md` — `CrashLoopBackOff` / `ImagePullBackOff` / `OOMKilled` / probe failures / `exec format error` / pending pods
- `references/schema-reference.md` — OpenAPI schemas worth looking up, credential type → key mappings, public-spec path-key quirks
- `references/lifecycle-flows.md` — artifact draft → lock → production flow rules and behavioral gotchas
- `references/code-to-workload.md` — deploy from source code (no Dockerfile authoring): `dr` CLI commands, `codeRef`, Execution Environments, generated vs provided Dockerfile modes, iterate-rebuild loop

## OpenAPI spec is source of truth

Published at `https://docs.datarobot.com/en/docs/api/reference/public-api/openapi.yaml`. **The spec is ~5 MB — never dump it whole into context.** Save once, then extract targeted slices with `yq`:

```bash
curl -sS "${DATAROBOT_ENDPOINT}/openapi.yaml" -o /tmp/wapi-spec.yaml
yq '.components.schemas.CreateWorkloadRequest' /tmp/wapi-spec.yaml
yq '.paths."/workloads/{workloadId}/".patch'    /tmp/wapi-spec.yaml
yq '.components.schemas | keys | .[]' /tmp/wapi-spec.yaml | grep -i workload   # discover
```

Python fallback: only `print()` the specific key, never the parsed dict. Path-key prefix quirk — see `references/schema-reference.md`.

---

# 1. Create / configure / scale

## Run a container as a workload (the 90% case)

```python
import os, httpx

base = os.environ["DATAROBOT_ENDPOINT"]
headers = {"Authorization": f"Bearer {os.environ['DATAROBOT_API_TOKEN']}"}

r = httpx.post(f"{base}/workloads/", headers=headers, json={
    "name": "my-api-service",
    "importance": "low",
    "artifact": {
        "name": "my-api-service-artifact",
        "spec": {
            "type": "service",
            "containerGroups": [{"containers": [{
                "name": "main",
                "imageUri": "ghcr.io/org/my-app:latest",
                "port": 8000,
                "primary": True,
                "readinessProbe": {"path": "/readyz", "port": 8000, "initialDelaySeconds": 10},
                "livenessProbe":  {"path": "/healthz", "port": 8000, "initialDelaySeconds": 30},
            }]}],
        },
    },
    "runtime": {"containerGroups": [{
        "name": "default",   # must match artifact.spec.containerGroups[].name
        "replicaCount": 1,
        "containers": [{"name": "main",
                        "resourceAllocation": {"cpu": 1, "memory": "512MB"}}],
    }]},
})
workload_id = r.json()["id"]
```

Then `python scripts/wait_for_running.py <workload_id>` to wait for `running`.

**Critical gotchas:**

- `importance`: `low` / `moderate` / `high` / `critical`. `type`: `service` (default) or `nim`. Exactly one container per group has `primary: true`.
- `cpu` is **cores** (float OK: `0.25`, `0.5`, `1`). `memory` accepts a decimal string (`"512MB"`, `"8GB"`, units B/KB/MB/GB) or a raw byte integer (`536870912`). Kubernetes-style binary suffixes (`Mi`, `Gi`) are NOT supported.
- `port` MUST be `>= 1024`. The container must actually listen on it (set via image env vars or entrypoint if defaults disagree).
- Image must include a **linux/amd64** manifest. Apple Silicon defaults to ARM64 and crash-loops with `exec format error`. Build with `docker buildx build --platform linux/amd64,linux/arm64 -t <ref> --push .`; verify with `docker buildx imagetools inspect <ref>`.
- Status lifecycle (full table in `references/status-vocabulary.md`): `submitted` → `provisioning` → `launching` → `running` (happy path); `updating` during rolling redeploys; `errored` recoverable; `failed`/`terminated` unrecoverable.

## "Update the workload" disambiguation

| User intent | Endpoint | Effect |
|---|---|---|
| Rename / redescribe / change importance | `PATCH /workloads/{id}/` | Metadata only — no restart |
| Change replicas / resources / autoscaling on the same artifact | `PATCH /workloads/{id}/settings/` | Triggers rolling redeploy |
| Deploy a different artifact (new image / version) | `POST /workloads/{id}/replacement/` | Rolling swap — see section 4 |

## Replicas, resources, autoscaling

`PATCH /workloads/{wid}/settings/` with `runtime.containerGroups[0]` — use exactly one of `replicaCount` (fixed) or `autoscaling`. Read settings first via `GET /workloads/{wid}/settings/` to see the current shape, then PATCH back. Autoscaling shape:

```json
{"autoscaling": {"enabled": true, "policies": [{
   "scalingMetric": "cpuAverageUtilization",
   "target": 70, "minCount": 1, "maxCount": 10}]}}
```

Valid `scalingMetric` values: `cpuAverageUtilization`, `httpRequestsConcurrency`, `gpuCacheUtilization`, `gpuRequestQueueDepth`, or a custom NIM metric. Settings updates are **rolling**; zero-downtime only with `replicaCount >= 2` (or autoscaling `minCount >= 2`).

## Org-set scaling limits — check before scaling

Each org has two admin-set caps: `maxConcurrentWorkloads` (max running workloads) and `maxWorkloadReplicas` (max replicas per workload). Users cannot change them; value `0` = unlimited. Read the effective limits via **`GET /account/info/`** → `limits` block (or `python scripts/check_limits.py`). The spec-documented `/users/{uid}/` and `/organizations/{id}/` paths require Admin API access (`403` for normal users) — `/account/info/` is the only one for regular users.

Exceeding either limit on `POST /workloads/`, `PATCH /workloads/{id}/settings/`, or autoscaling `maxCount` returns **HTTP 403** with `{"detail": "Requested replicas (N) exceeds the maximum allowed (M)."}`. When a user asks to scale beyond what's possible, **check limits first**, then propose the max allowed value or note that admin help is needed. Schema details in `references/schema-reference.md`.

## GPU type / VRAM = compute bundle (not direct)

`resourceAllocation` only accepts `cpu`, `memory`, and `gpu` *count*. There is no `gpuType` or `gpuMemory` field. To target a GPU model or VRAM size:

1. `GET /mlops/compute/bundles/` — lists bundles like `cpu.small`, `gpu.l4.small`, `gpu.a10g.medium`.
2. Pass via `resourceBundles` (a list for API compatibility, but **exactly one** bundle allowed): `"resourceBundles": ["gpu.l4.small"]` under the container group.

When a bundle is set, CPU and memory in `resourceAllocation` are ignored; the bundle defines them.

## Credential injection — never hardcode secrets

DataRobot credentials are stored centrally and injected into `environmentVars` by reference:

```python
"environmentVars": [
    {"name": "PLAIN_VAR", "value": "literal-value"},
    {"source": "dr-credential", "name": "AWS_ACCESS_KEY_ID",
     "drCredentialId": "<credential-id>", "key": "awsAccessKeyId"},
]
```

Workflow: `GET /credentials/?limit=50` → find the credential ID and its `credentialType` → look up the `key` field names for that type. See `references/schema-reference.md` for the full type-to-keys table (`s3`, `basic`, `api_token`, `bearer`, `oauth`, `gcp`, `azure_service_principal`, `databricks_*`, `snowflake_*`, …).

## Create from an existing artifact

Provide `artifactId` instead of the inline `artifact` block. The `containerGroups[].name` and `containers[].name` in `runtime` must match what the artifact defines.

---

# 2. Diagnose — workload is stuck, errored, or crash-looping

## One command for the full diagnosis

```bash
python scripts/diagnose_workload.py <workload_id>
```

Runs all 5 steps below, prints a structured report (status / logTail signals / flagged events / proton K8s detail / evidence / recommended next step / console URL). `--json` for machine-readable.

If the script's `Evidence` is empty, pull application logs via section 3 — don't guess from status alone.

## The 5-step flow

The script encapsulates this; here's the model an agent needs when output is ambiguous or a one-off call is needed.

1. **`GET /workloads/{id}/`** — `status`, `statusDetails.logTail` (~30 lines), `statusDetails.conditions`. Scan `logTail` for `error` / `exception` / `traceback` / `killed` / `permission denied` / `connection refused`. Guard `statusDetails` with `(w.get("statusDetails") or {})` — it can be `null` during `submitted` / `provisioning`.
2. **`GET /workloads/{id}/events/`** — flag any event with `type: Warning` or `reason` containing `Failed` / `Error` / `Kill` / `OOM`. The last `Warning` before `errored` is usually the trigger.
3. **`GET /workloads/{id}/protons/`** — pick `role: "active"`. During a rolling replacement debug the `candidate` instead if that's what's failing. If no active role, take the most recent `createdAt`.
4. **`GET /workloads/{id}/protons/{pid}/statusDetails/`** — returns `204` while still initializing; that's not an error. Once populated, read in this order: `replicas[*].containers[*].status` + `restartCount` (the headline) → `replicas[*].conditions[*]` (any `value: false` is a smoking gun) → `overallStatus.summary` (DataRobot's human-readable interpretation).
5. **Application logs** — section 3.

Common patterns (`CrashLoopBackOff`, `ImagePullBackOff`, `OOMKilled`, probe failures, pending pods, `exec format error`) and their fix paths: `references/common-error-patterns.md`.

## Reporting findings

```
Workload {id} — Diagnosis
- Status: {current}
- Root cause: {one sentence}
- Evidence: {the specific logTail line, condition, container reason, or event}
- Recommended fix: {actionable next step — section 1 (settings), section 4 (artifact), or app code}
- Console: https://app.datarobot.com/console-nextgen/workloads/{id}/overview
```

---

# 3. Observe — logs, traces, metrics, service stats

| Stream | Endpoint | Needs app instrumentation? |
|---|---|---|
| Logs | `/otel/workload/{id}/logs/` | No — auto from stdout/stderr |
| Traces | `/otel/workload/{id}/traces/` | **Yes** (OTEL spans) |
| Metrics | `/otel/workload/{id}/metrics/autocollectedValues/` | Partially |
| Service stats | `/workloads/{id}/stats/` | No — DataRobot edge proxy |
| Replacement history | `/workloads/{id}/history/` | No — platform |
| Lifecycle events | `/workloads/{id}/events/` | No — platform |

Always check `r.status_code` before `.json()`: 401 = bad token; 404 = workload not found; 429 = rate limited (exponential backoff). All list endpoints accept `limit` + `offset`.

## Logs

```python
r = httpx.get(f"{base}/otel/workload/{wid}/logs/", headers=headers, params={
    "limit": 100,
    "level": "error",          # EXACT severity (not a threshold) — pass "error" to triage errors
    "includes": "traceback",   # case-sensitive substring on message body
})
for log in r.json().get("data", []):
    print(f"[{log['timestamp']}] {log['level'].upper()}: {log['message']}")
```

To filter to one proton (find proton IDs in section 2): `params = {"limit": 100, "searchKeys": "proton_id", "searchValues": "<pid>"}`. `searchKeys`/`searchValues` are positional parallel lists — repeat the param to filter on multiple attributes (not comma-joined).

## Traces

```python
traces = httpx.get(f"{base}/otel/workload/{wid}/traces/", headers=headers).json()["data"]
# summary: traceId, rootSpanName, rootServiceName, duration (NANOSECONDS), spansCount, errorSpansCount
trace_id = next((t["traceId"] for t in traces if t.get("errorSpansCount", 0) > 0), traces[0]["traceId"])
trace = httpx.get(f"{base}/otel/workload/{wid}/traces/{trace_id}/", headers=headers).json()
```

> **`duration` is NANOSECONDS** on summaries AND spans. Divide by 1,000,000 for ms before display. Empty `data` = app isn't instrumented; direct the user to wire up OTEL.

## Metrics + service stats

Metrics unit conversions before display: `bytes` → MB (`/ 1024**2`); `nanocores` → cores (`/ 1_000_000`); `percentage` already a %.

Service stats response shape:

```python
stats = httpx.get(f"{base}/workloads/{wid}/stats/", headers=headers).json()
# {
#   "period":  {"start": "...", "end": "..."},
#   "metrics": {"totalRequests": ..., "serverErrors": ..., "userErrors": ..., "slowRequests": ...,
#               "responseTime": ..., "requestsPerMinute": ..., "concurrentRequests": ...,
#               "totalErrorRate": ..., "serverErrorRate": ..., "userErrorRate": ...}
# }
```

`GET /workloads/stats/` (aggregate across all workloads) uses the same shape.

> **Warning — destructive.** `DELETE /workloads/{id}/stats/?metricName=<name>` zeroes a metric's history. Only call when the user explicitly asks to reset stats.

## Presenting results

- **Logs:** `timestamp | level | message`, group `ERROR`/`CRITICAL` first, truncate over 300 chars.
- **Traces:** table `traceId | rootService/rootSpan | duration_ms | spans | errors`, sort by errors desc then recency.
- **Metrics:** `displayName | currentValue (converted) | unit`.
- **Service stats:** *"`{totalRequests}` requests, `{totalErrorRate*100:.2f}%` error rate (server `{serverErrors}` / user `{userErrors}`), `{responseTime:.1f}` ms avg, `{requestsPerMinute}` req/min."*

Empty `data` → say *why* (not running yet / not instrumented / time window empty), don't just "no data".

---

# 4. Artifact lifecycle

An **artifact** is the immutable-after-lock definition of what a workload runs (image, port, env vars, probes). A **workload** is the running instance + its runtime (replicas, resources, autoscaling). Resources do NOT belong on the artifact.

## Picking the right path

To change a running workload's image / env vars / probes / port, find its current artifact (`workload["artifactId"]`) and check `artifact["status"]`. If `draft`: PATCH in place → `POST /workloads/{id}/replacement/`. If `locked`: clone → PATCH the clone → lock it → `POST /workloads/{id}/replacement/`.

**Replacement status-match rule:** rejected with 400 unless the new artifact's status matches the running one's. draft↔draft, locked↔locked. To go from draft to production WITHOUT a restart, use `POST /workloads/{id}/promote/` (atomic lock-in-place; pods are NOT restarted).

For runtime-only changes (replicas / resources / autoscaling), use section 1's `PATCH /workloads/{id}/settings/`; don't touch the artifact. **Patching an artifact does NOT affect running workloads** — trigger a replacement (or `promote`) to apply changes to live workloads. Full code in `references/lifecycle-flows.md`.

## How does your image get to DataRobot?

The Workload API does **not yet accept image-pull credentials at workload creation** — the artifact's `imageUri` must point at a registry DataRobot can already pull from. Two paths:

1. **Bring your own image** — when the image lives in a public registry (`ghcr.io/org/app:tag`, Docker Hub public) or one the org admin pre-configured. Build locally with `docker buildx ... --platform linux/amd64`, push, reference via `imageUri`. The default flow used throughout this skill.
2. **Code-to-Workload (C2W)** — when you can't publish (no local Docker, no public registry, admin can't add pull credentials). The `dr` CLI uploads source code (`dr workload code init` + `code sync`); `POST /artifacts/{id}/builds` triggers a platform build that pushes to DataRobot's **internal** registry and populates `imageUri`. From there, identical to bring-your-own-image. Full flow in `references/code-to-workload.md`.

Poll either path with `python scripts/wait_for_build.py <artifact_id> <build_id>`. Only drafts can build.

> **C2W is preview / feature-flagged** — needs `ENABLE_WORKLOAD_API_CONTAINERS=true` on the org and `DATAROBOT_CLI_FEATURE_WORKLOAD=true` client-side. Steps may change before GA.

## Rolling artifact replacement

```python
httpx.post(f"{base}/workloads/{wid}/replacement/", headers=headers, json={
    "artifactId": new_artifact_id,
    "strategy": "rolling",                   # only "rolling" supported
    "config": {                              # OPTIONAL — omit for platform defaults
        "warmupDurationMinutes": 2,          # warm caches; 0 to skip
        "keepOldVersionMinutes": 5,          # rollback window; 0 to drop immediately
    },
    # Optional — change runtime in the same call (same shape as PATCH /settings/)
    # "runtime": {"containerGroups": [{"name": "default", "replicaCount": 3}]}
})
```

Then `python scripts/wait_for_replacement.py <workload_id>` to monitor.

`GET /workloads/{id}/replacement/` returns **404** when no active replacement (body: `{"detail": "There is no active replacement for this workload."}`) — that's "no replacement in progress", not an error. Cancel an in-progress one with `DELETE`. **Not idempotent**: calling `POST` while one is in progress queues a second swap — always check via the script first.

---

## Related skills

- `datarobot-setup` — install SDK, configure auth, set env vars
- `datarobot-app-framework-cicd` — declarative artifact + workload management via Pulumi and CI/CD
- `datarobot-external-agent-monitoring` — instrument arbitrary agent code with OTEL → DataRobot
