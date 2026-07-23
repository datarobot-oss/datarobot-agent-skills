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

SKILL.md is the operational core; occasional detail lives in `references/`:

- `status-vocabulary.md` — workload + proton status enums and transitions
- `common-error-patterns.md` — CrashLoopBackOff / ImagePullBackOff / OOMKilled / probe / exec-format / pending
- `schema-reference.md` — schemas to look up, credential-type→key maps, public-spec path quirks
- `lifecycle-flows.md` — artifact draft→lock→prod rules, replacement preconditions, redeploy matrix, `imageUri` gotchas
- `code-to-workload.md` — deploy from source: `dr` CLI, `codeRef`, Execution Environments, iterate-rebuild loop
- `web-uis-behind-the-edge.md` — browser-facing web app through the endpoint: prefix stripping, auth gate, `Authorization` hijack, shim, CSRF, WebSockets

## OpenAPI spec is source of truth

At `${DATAROBOT_ENDPOINT}/openapi.yaml`. **~5 MB — never dump it whole.** Save once, then slice with `yq` (or `print()` only the specific key in Python):

```bash
curl -sS "${DATAROBOT_ENDPOINT}/openapi.yaml" -o /tmp/wapi-spec.yaml
yq '.components.schemas.CreateWorkloadRequest' /tmp/wapi-spec.yaml
yq '.components.schemas | keys | .[]' /tmp/wapi-spec.yaml | grep -i workload   # discover
```

All workload paths are keyed with the `/api/v2/` prefix — see `references/schema-reference.md`.

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

## Serving a browser-facing web UI through the endpoint

If the container serves a **web app (UI + its own backend/API/WebSocket)** opened in a browser via `dr workload endpoint <id>` (not a headless service), the DataRobot edge gateway serves it under a path prefix and: **strips the prefix inbound** (no outbound rewrite — the app must be sub-path aware); **is the auth gate** (DataRobot login required) and **hijacks the `Authorization` header** (→ `401 {"message":"Invalid API key"}`, never reaching the container); **passes WebSockets through**. Winning pattern: set the app's base-path to the prefix + re-add it inbound (derive it from the injected `WORKLOAD_ID`), **disable the app's own auth (trust the edge)**, disable CSRF, probe an unauthenticated path. Full guidance, shim code, and per-symptom diagnostics: `references/web-uis-behind-the-edge.md`.

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

The script encapsulates this; use the model below for ambiguous output or one-off calls.

1. **`GET /workloads/{id}/`** — `status`, `statusDetails.logTail` (~30 lines; scan for `error`/`exception`/`traceback`/`killed`/`permission denied`/`connection refused`), `statusDetails.conditions`. Guard `statusDetails` — it's `null` during `submitted`/`provisioning`.
2. **`GET /workloads/{id}/events/`** — flag `type: Warning` or `reason` with `Failed`/`Error`/`Kill`/`OOM`; the last Warning before `errored` is usually the trigger.
3. **`GET /workloads/{id}/protons/`** — pick `role: "active"` (or the `candidate` during a rolling replacement; else newest `createdAt`).
4. **`GET /workloads/{id}/protons/{pid}/statusDetails/`** — `204` while initializing (not an error). Read `replicas[*].containers[*].status`+`restartCount` → `replicas[*].conditions[*]` (any `value:false`) → `overallStatus.summary`.
5. **Application logs** — section 3.

Common patterns (`CrashLoopBackOff`, `ImagePullBackOff`, `OOMKilled`, probe/pending, `exec format error`) and fixes: `references/common-error-patterns.md`.

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

Convert before display: `bytes`→MB (`/1024**2`), `nanocores`→cores (`/1_000_000`), `percentage` already %.

```python
stats = httpx.get(f"{base}/workloads/{wid}/stats/", headers=headers).json()
# {"period": {...}, "metrics": {totalRequests, serverErrors, userErrors, slowRequests,
#   responseTime, requestsPerMinute, concurrentRequests, *ErrorRate}}. /workloads/stats/ = aggregate.
```

> **Destructive:** `DELETE /workloads/{id}/stats/?metricName=<name>` zeroes a metric's history — only on explicit request.

## Presenting results

Logs: `timestamp | level | message`, ERROR/CRITICAL first. Traces: table sorted by errors desc then recency. Metrics: apply unit conversion before display. Service stats one-liner: *"`{totalRequests}` requests, `{totalErrorRate*100:.2f}%` errors, `{responseTime:.1f}` ms avg, `{requestsPerMinute}` req/min."* Empty data → say *why* (not running, not instrumented, empty window), don't just "no data".

---

# 4. Artifact lifecycle

An **artifact** is the immutable-after-lock definition of what a workload runs (image, port, env vars, probes). A **workload** is the running instance + its runtime (replicas, resources, autoscaling). Resources do NOT belong on the artifact.

## Picking the right path

Find the running artifact (`workload["artifactId"]`), check `artifact["status"]`. A running workload does **not** auto-adopt a rebuild until you redeploy.

- **Same draft (the C2W loop) — in-place change or rebuild.** PATCH/rebuild the draft, then roll onto it with `PATCH /workloads/{id}/settings/`: re-send the runtime body (even unchanged values trigger a rolling `202` redeploy that re-reads the current spec + latest `COMPLETED` build). Zero-downtime at ≥2 replicas. (`POST /replacement/` onto the same draft also works.)
- **Different / locked artifact.** `POST /replacement/` onto the other artifact ID. Locked in-place edit: clone → PATCH clone → lock → replace onto the clone.

**Lock:** `dr artifact lock <id>` (= `PATCH /artifacts/{id}/ {"status":"locked"}`). **Promote** (`POST /workloads/{wid}/promote/`, 200) locks the running draft in place, no restart. Runtime-only changes (replicas/resources/autoscaling) → `PATCH /settings/`; a PATCH to the artifact doesn't affect live workloads until you redeploy.

Preconditions (status-match, same-artifact rule) and the full redeploy matrix: `references/lifecycle-flows.md`.

## How does your image get to DataRobot?

The artifact's `imageUri` must point at a registry DataRobot can pull from (image-pull creds aren't accepted at workload creation yet). Two paths:

1. **Bring your own image** — public registry or one the admin pre-configured. `docker buildx ... --platform linux/amd64`, push, set `imageUri`. Default flow.
2. **Code-to-Workload (C2W)** — no local Docker / no public registry: `dr artifact code init` + `sync`, then `dr artifact build create` builds server-side, pushes to DataRobot's internal registry, and populates `imageUri`. Full flow in `references/code-to-workload.md`.

Poll builds with `python scripts/wait_for_build.py <artifact_id> <build_id>`; only drafts build. **`imageUri` is build-managed** — never PATCH it by hand (`422` "not permitted on this cluster"), and never PATCH the spec *mid-build* (a whole-spec write clobbers the pending build image → redeploys the old one). Sequence spec edits before `build create` or after `COMPLETED`.

> **C2W is preview / feature-flagged** — `ENABLE_WORKLOAD_API_CONTAINERS=true` (org) + `DATAROBOT_CLI_FEATURE_WORKLOAD=true` (client).

## Rolling artifact replacement

```python
httpx.post(f"{base}/workloads/{wid}/replacement/", headers=headers, json={
    "artifactId": new_artifact_id,
    "strategy": "rolling",                   # only "rolling" supported
    "config": {"warmupDurationMinutes": 2, "keepOldVersionMinutes": 5},  # optional
    # "runtime": {...}  # optional; same shape as PATCH /settings/
})
```

Monitor with `python scripts/wait_for_replacement.py <workload_id>`. Preconditions: status must match (draft↔draft / locked↔locked, else `400`); same-artifact replacement 422s for locked but works for drafts — to roll the same draft without replacement use `PATCH /settings/`. **Not idempotent** (a second `POST` queues another swap); `GET .../replacement/` `404` = none in progress; `DELETE` to cancel. Detail in `references/lifecycle-flows.md`.

---

## Related skills

- `datarobot-setup` — install SDK, configure auth, set env vars
- `datarobot-app-framework-cicd` — declarative artifact + workload management via Pulumi and CI/CD
- `datarobot-external-agent-monitoring` — instrument arbitrary agent code with OTEL → DataRobot
