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
yq '.paths."/api/v2/workloads/{workload_id}/".patch' /tmp/wapi-spec.yaml
yq '.components.schemas | keys | .[]' /tmp/wapi-spec.yaml | grep -i workload   # discover
```

Python fallback: only `print()` the specific key, never the parsed dict. All workload paths in the public spec are keyed with `/api/v2/` prefix — see `references/schema-reference.md`.

---

# 1. Create / configure / scale

## Run a container as a workload (the 90% case)

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
dr workload create --spec-file spec.yaml         # v0.2.74+; 4xx: 400=schema/limit, 403=cap (run check_limits.py), 409=name conflict
dr workload get <workload_id>                    # or `dr workload status` — poll until status=running
```

Lifecycle one-liners (v0.2.74+): `dr workload {stop|start|delete|endpoint|list} <id>`.

Raw fallback when CLI unavailable: `httpx.post(f"{base}/workloads/", headers=headers, json=spec)` + `r.raise_for_status()` + `r.json()["id"]`. Then `python scripts/wait_for_running.py <workload_id>`.

**Critical gotchas:**

- `importance`: `low`/`moderate`/`high`/`critical`; `type`: `service` (default) or `nim`. Exactly one container per group has `primary: true`.
- `cpu` is cores (float OK). `memory` accepts decimal string (`"512MB"`, units B/KB/MB/GB) or byte integer; Kubernetes binary suffixes (`Mi`/`Gi`) NOT supported.
- `port` MUST be `>= 1024`. The container must actually listen on it (set via image env vars or entrypoint).
- Image must include a **linux/amd64** manifest. Apple Silicon defaults to ARM64 and crash-loops with `exec format error`. Build with `docker buildx build --platform linux/amd64,linux/arm64 -t <ref> --push .`.
- Status lifecycle: `submitted` → `provisioning` → `launching` → `running` (happy path); `updating` during rolling redeploys; `errored` recoverable; `failed`/`terminated` unrecoverable. Full table in `references/status-vocabulary.md`.

## "Update the workload" disambiguation

| User intent | Endpoint | Effect |
|---|---|---|
| Rename / redescribe / change importance | `PATCH /workloads/{id}/` | Metadata only — no restart |
| Change replicas / resources / autoscaling on the same artifact | `PATCH /workloads/{id}/settings/` | Triggers rolling redeploy |
| Deploy a different artifact (new image / version) | `POST /workloads/{id}/replacement/` | Rolling swap — see section 4 |

## Replicas, resources, autoscaling

`PATCH /workloads/{wid}/settings/` with full body shape — use exactly one of `replicaCount` or `autoscaling`. Read settings first via `GET /workloads/{wid}/settings/`, then PATCH back:

```python
httpx.patch(f"{base}/workloads/{wid}/settings/", headers=headers, json={
    "runtime": {"containerGroups": [{
        "name": "default", "replicaCount": 3,
        "containers": [{"name": "main", "resourceAllocation": {"cpu": 2, "memory": "1GB"}}],
        # OR: "autoscaling": {"enabled": True, "policies": [{
        #       "scalingMetric": "cpuAverageUtilization",
        #       "target": 70, "minCount": 1, "maxCount": 10}]}
    }]}
})
```

Valid `scalingMetric` values: `cpuAverageUtilization`, `httpRequestsConcurrency`, `gpuCacheUtilization`, `gpuRequestQueueDepth`, or a custom NIM metric. Settings updates are **rolling**; zero-downtime only with `replicaCount >= 2` (or autoscaling `minCount >= 2`).

## Org-set scaling limits — check before scaling

Two admin-set caps: `maxConcurrentWorkloads` and `maxWorkloadReplicas`. Value `0` = unlimited; users can't change them. Read via **`GET /account/info/`** — response includes `{"limits": {"maxConcurrentWorkloads": N, "maxWorkloadReplicas": M}}` (or `python scripts/check_limits.py`). The spec's `/users/{uid}/` and `/organizations/{id}/` paths require Admin API access. Exceeding either limit returns **HTTP 403** with `{"detail": "Requested replicas (N) exceeds the maximum allowed (M)."}` — check limits first, then propose the max allowed or flag that admin help is needed.

## GPU type / VRAM — set via compute bundle, not direct

`resourceAllocation` only accepts `cpu`, `memory`, `gpu` (count). There is NO `gpuType` or `gpuMemory` field. To target a GPU model / VRAM size: `GET /mlops/compute/bundles/` lists bundles (`cpu.small`, `gpu.l4.small`, `gpu.a10g.medium`); pass via `"resourceBundles": ["gpu.l4.small"]` (a list, but exactly ONE bundle allowed) under the container group. When a bundle is set, CPU/memory in `resourceAllocation` are ignored — the bundle defines them.

## Credential injection — never hardcode secrets

DataRobot credentials are stored centrally and injected into `environmentVars` by reference:

```python
"environmentVars": [
    {"name": "PLAIN_VAR", "value": "literal-value"},
    {"source": "dr-credential", "name": "AWS_ACCESS_KEY_ID",
     "drCredentialId": "<credential-id>", "key": "awsAccessKeyId"},
]
```

Workflow: `GET /credentials/?limit=50` → note the credential's `credentialType` → look up the valid `key` field names for that type in `references/schema-reference.md` (covers `s3`, `basic`, `api_token`, `bearer`, `oauth`, `gcp`, `azure_*`, `databricks_*`, `snowflake_*`, …).

## Create from an existing artifact

Provide `artifactId` instead of the inline `artifact` block. The `containerGroups[].name` and `containers[].name` in `runtime` must match what the artifact defines.

---

# 2. Diagnose — workload is stuck, errored, or crash-looping

## One command for the full diagnosis

```bash
python scripts/diagnose_workload.py <workload_id>
```

Runs all 5 steps below, prints a structured report (status / logTail signals / flagged events / proton K8s detail / evidence / recommended next step / console URL). `--json` for machine-readable. If `Evidence` is empty, pull application logs via section 3 — don't guess from status alone.

## The 5-step flow

The script encapsulates this; here's the model for ambiguous output or one-off calls.

1. **`GET /workloads/{id}/`** — `status`, `statusDetails.logTail` (~30 lines), `statusDetails.conditions`. Scan `logTail` for `error` / `exception` / `traceback` / `killed` / `permission denied` / `connection refused`. Guard `statusDetails` with `(w.get("statusDetails") or {})` — it can be `null` during `submitted` / `provisioning`.
2. **`GET /workloads/{id}/events/`** — flag any event with `type: Warning` or `reason` containing `Failed` / `Error` / `Kill` / `OOM`. The last `Warning` before `errored` is usually the trigger.
3. **`GET /workloads/{id}/protons/`** — response: `{"data": [{"id": "...", "role": "active"|"candidate"|"retiring", "createdAt": "..."}]}`. Pick `role: "active"`; during a rolling replacement debug the `candidate` if that's what's failing. If no active role, take the most recent `createdAt`.
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

```bash
dr workload logs <wid> --level error --limit 100   # v0.2.74+; --follow streams; --output-format json
```

`--level` is an EXACT severity match (not a threshold). For substring filtering on the message body, or proton-scoped logs (find proton IDs in section 2), drop to REST — `dr workload logs` doesn't expose those filters:

```python
r = httpx.get(f"{base}/otel/workload/{wid}/logs/", headers=headers,
              params=[("searchKeys", "proton_id"), ("searchValues", pid),
                      ("searchKeys", "level"),     ("searchValues", "error")])
```

`searchKeys` / `searchValues` are positional parallel lists — pass a **list of tuples** to httpx (dict can't repeat keys). `includes=<substring>` does case-sensitive substring filtering on the message body.

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
# Returns {"period": {start, end}, "metrics": {totalRequests, serverErrors, userErrors,
#   slowRequests, responseTime, requestsPerMinute, concurrentRequests, totalErrorRate,
#   serverErrorRate, userErrorRate}}.  /workloads/stats/ (aggregate) same shape.
```

> **Warning — destructive.** `DELETE /workloads/{id}/stats/?metricName=<name>` zeroes a metric's history. Only call when the user explicitly asks to reset stats.

## Presenting results

Logs: `timestamp | level | message`, ERROR/CRITICAL first. Traces: table sorted by errors desc then recency. Metrics: apply unit conversion before display. Service stats one-liner: *"`{totalRequests}` requests, `{totalErrorRate*100:.2f}%` errors, `{responseTime:.1f}` ms avg, `{requestsPerMinute}` req/min."* Empty data → say *why* (not running, not instrumented, empty window), don't just "no data".

---

# 4. Artifact lifecycle

An **artifact** is the immutable-after-lock definition of what a workload runs (image, port, env vars, probes). A **workload** is the running instance + its runtime (replicas, resources, autoscaling). Resources do NOT belong on the artifact.

## Picking the right path

To change a running workload's image / env vars / probes / port, find its current artifact (`workload["artifactId"]`) and check `artifact["status"]`. If `draft`: PATCH in place → `POST /workloads/{id}/replacement/`. If `locked`: clone → PATCH the clone → lock it → `POST /workloads/{id}/replacement/`.

**Lock an artifact:** `dr artifact lock <id>` (v0.2.74+) — equivalent to `PATCH /artifacts/{id}/ {"status": "locked"}`. No `POST /artifacts/{id}/lock/`. For a draft already running on a workload, use `promote` (no restart).

**Replacement status-match rule:** `400 {"detail": "Artifact status mismatch: ..."}` unless the new artifact's status matches the running one's. draft↔draft, locked↔locked. Check before calling.

**Promote (no restart):** `POST /workloads/{wid}/promote/` (empty body, returns 200) locks the draft the workload is currently running, in place. No pod restart. Only valid if the workload already runs that artifact — for a *different* one, use replacement.

For runtime-only changes (replicas / resources / autoscaling), use section 1's `PATCH /workloads/{id}/settings/`; don't touch the artifact. **Patching an artifact does NOT affect running workloads** — trigger a replacement (or `promote`) to apply changes to live workloads. Full code in `references/lifecycle-flows.md`.

## How does your image get to DataRobot?

The Workload API does **not yet accept image-pull credentials at workload creation** — the artifact's `imageUri` must point at a registry DataRobot can already pull from. Two paths:

1. **Bring your own image** — when the image lives in a public registry (`ghcr.io/org/app:tag`, Docker Hub public) or one the org admin pre-configured. Build locally with `docker buildx ... --platform linux/amd64`, push, reference via `imageUri`. The default flow used throughout this skill.
2. **Code-to-Workload (C2W)** — when you can't publish (no local Docker, no public registry, admin can't add pull credentials). `dr` CLI v0.2.74+ uploads source (`dr artifact code init` + `sync`), `dr artifact build create` triggers a platform build that pushes to DataRobot's **internal** registry and populates `imageUri`. From there, identical to bring-your-own-image. Full flow in `references/code-to-workload.md`.

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
