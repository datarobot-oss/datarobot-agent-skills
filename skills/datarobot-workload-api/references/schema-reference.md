# Schema reference (non-spec content)

The public OpenAPI spec at `${DATAROBOT_ENDPOINT}/openapi.yaml` is the source of truth for all schemas and endpoints. **~5 MB — never load whole into agent context.** Save once, extract targeted slices with `yq`:

> **Some instances don't expose the Workload API in this spec at all.** A spec pull can come back with no `/workloads` or `/artifacts` paths (only e.g. `/files/fromFile/`), even though the endpoints work. If `yq`/grepping the saved spec turns up nothing for a path or schema this skill describes, don't conclude the endpoint doesn't exist — this skill's own content (SKILL.md + `references/`) is the fallback source of truth, and the live `GET`/PATCH response shape is ground truth. A spec/API divergence is expected on some clusters, not a reason to distrust the request.

```bash
curl -sS "${DATAROBOT_ENDPOINT}/openapi.yaml" -o /tmp/wapi-spec.yaml
yq '.components.schemas.CreateWorkloadRequest' /tmp/wapi-spec.yaml     # schema body
yq '.paths."/workloads/{workloadId}/".patch'    /tmp/wapi-spec.yaml     # endpoint params
yq '.components.schemas | keys | .[]' /tmp/wapi-spec.yaml | grep -i otel   # discover names
```

No `yq`: fall back to Python — but only `print()` the specific key (`spec["components"]["schemas"]["X"]`), never the parsed `spec` dict itself.

This file holds only what the spec **doesn't** document: authorization quirks, runtime constraints not enforced at the schema level, and aggregate tables that would otherwise mean repeated grepping.

## Org-set scaling limits — authorization

`maxConcurrentWorkloads` and `maxWorkloadReplicas` exist on three schemas — `OrganizationRetrieve`, `OrganizationUserResponse`, `UserRetrieveResponse` — but the endpoints returning them (`GET /organizations/{id}/`, `GET /organizations/{id}/users/{uid}/`, `GET /users/{uid}/`) all need **Admin API access**: `403 {"message": "You do not have Admin API access permissions"}` for normal users, even self-lookup on `/users/{uid}/`.

The only path a regular user has: **`GET /account/info/`**, returning the **already-resolved effective limits** in a `limits` block:

```json
{"limits": {"maxConcurrentWorkloads": 50, "maxWorkloadReplicas": 3}}
```

Or `python scripts/check_limits.py`. `0` = unlimited; any non-zero is enforced. Exceeding either limit on `POST /workloads/`, `PATCH /workloads/{id}/settings/`, or autoscaling `maxCount`: **HTTP 403** `{"detail": "Requested replicas (N) exceeds the maximum allowed (M)."}`. Both fields added in spec v2.46.

## Public-spec path-key prefix quirk

The published spec at `https://docs.datarobot.com/en/docs/api/reference/public-api/openapi.yaml` aggregates multiple internal specs, inconsistent about path-key prefixing. Runtime URLs are unaffected (`${DATAROBOT_ENDPOINT}` already includes `/api/v2`), but **spec lookups** need to know:

| Path namespace | Keyed in spec as | Example |
|---|---|---|
| Workloads + artifacts | **with** `/api/v2/` | `/api/v2/workloads/{workload_id}/protons/{proton_id}/statusDetails` |
| OTEL (workload telemetry) | **with** `/api/v2/`, and **templated** | `/api/v2/otel/{entityType}/{entityId}/logs/` (`{entityType}` = literal `workload`) |
| Credentials | **with** `/api/v2/` | `/api/v2/credentials/` |
| Compute bundles | **with** `/api/v2/` | `/api/v2/mlops/compute/bundles/` |

Grepping `spec["paths"]`: try both shapes on a miss. Runtime calls are always `${DATAROBOT_ENDPOINT}/<rest of path>` regardless.

## Credential types and `key` field names

Used in `environmentVars` entries shaped as `{"source": "dr-credential", "name": "<env var>", "drCredentialId": "<id>", "key": "<key below>"}`. Aggregates fields otherwise found only by grepping each `*Credentials` schema individually.

| `credentialType` | Available `key` field names |
|---|---|
| `s3` | `awsAccessKeyId`, `awsSecretAccessKey`, `awsSessionToken` |
| `basic` | `user`, `password` |
| `api_token` | `apiToken` |
| `bearer` | `token` |
| `oauth` | `token`, `refreshToken` |
| `gcp` | `gcpKey` |
| `azure_service_principal` | `azureTenantId`, `clientId`, `clientSecret` |
| `azure` | `azureConnectionString` |
| `databricks_access_token_account` | `databricksAccessToken` |
| `snowflake_key_pair_user_account` | `privateKeyStr`, `passphrase`, `user` |

Credential type not listed: fetch the spec, look up `<Type>Credentials` (e.g. `S3Credentials`, `BasicCredentials`, `OAuthCredentials`) — schema properties are the valid `key` values.

## Sharing — role values are UPPERCASE, not the lowercase the docs show

`PATCH /workloads/{id}/sharedRoles` (and the equivalent GET) uses roles from the wider platform sharing enum. The Sharing and access control docs give lowercase examples (`owner`, `user`, `consumer`); the API rejects those with **`422`**, listing accepted values in the error body: `OWNER`, `USER`, `CONSUMER` (uppercase). Use uppercase.

The call **replaces the entire role list** — not a delta/merge. Read current roles first, include the owner (and anyone else who should keep access) in the PATCH body, or they lose access.

## Schemas where the read model and write model diverge

Non-obvious naming/divergence:

- **Artifacts:** read body is `ArtifactFormatted`; PATCH write body is `UpdateArtifactRequest`, **does NOT accept `spec.type`** (read-only discriminator). `MultiContainerArtifactSpec` covers the `spec` object both ways.
- **Artifact creation:** no `CreateArtifactRequest` schema. Artifacts are created inline via `CreateWorkloadRequest.artifact`, or by cloning via `ArtifactCloneRequest` (word order — not `CloneArtifactRequest`).
- **Replacement:** `POST` body is `StartReplacementRequest`; optional `config` block is `ReplacementConfig`. Only `strategy: "rolling"` supported.
- **Image builds:** read body is `ImageBuildFormatted`; build config on the artifact is `ImageBuildConfig`. Success status can be `BUILT` or `COMPLETED` depending on platform version — treat both as terminal-success.
