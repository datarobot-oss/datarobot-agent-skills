# Schema reference (non-spec content)

The public OpenAPI spec at `${DATAROBOT_ENDPOINT}/openapi.yaml` is the source of truth for all schemas and endpoints. **The spec is ~5 MB — never load it whole into agent context.** Save once and extract targeted slices with `yq`:

> **Some instances don't expose the Workload API in this spec at all.** A spec pull can come back with no `/workloads` or `/artifacts` paths (only e.g. `/files/fromFile/`), even though the endpoints work. If `yq`/grepping the saved spec turns up nothing for a path or schema this skill describes, don't conclude the endpoint doesn't exist — this skill's own operational content (SKILL.md + `references/`) is the fallback source of truth, and the live `GET`/PATCH response shape is the ultimate ground truth. Treat a divergence between the spec and what the API actually returns as expected on some clusters, not a sign to distrust the request you're about to make.

```bash
curl -sS "${DATAROBOT_ENDPOINT}/openapi.yaml" -o /tmp/wapi-spec.yaml
yq '.components.schemas.CreateWorkloadRequest' /tmp/wapi-spec.yaml     # schema body
yq '.paths."/workloads/{workloadId}/".patch'    /tmp/wapi-spec.yaml     # endpoint params
yq '.components.schemas | keys | .[]' /tmp/wapi-spec.yaml | grep -i otel   # discover names
```

If `yq` isn't available, fall back to Python — but only `print()` the specific key (`spec["components"]["schemas"]["X"]`), never the parsed `spec` dict itself.

This file holds only the things the spec **doesn't** document: authorization quirks, runtime constraints not enforced at the schema level, and aggregate tables that would otherwise require repeated grepping.

## Org-set scaling limits — authorization

`maxConcurrentWorkloads` and `maxWorkloadReplicas` exist on three schemas in the spec — `OrganizationRetrieve`, `OrganizationUserResponse`, `UserRetrieveResponse` — but the endpoints that return them (`GET /organizations/{id}/`, `GET /organizations/{id}/users/{uid}/`, `GET /users/{uid}/`) all require **Admin API access** and return `403 {"message": "You do not have Admin API access permissions"}` for normal users, even for self-lookup on `/users/{uid}/`.

The only path a regular user has is **`GET /account/info/`**, which returns the **already-resolved effective limits** in a `limits` block:

```json
{"limits": {"maxConcurrentWorkloads": 50, "maxWorkloadReplicas": 3}}
```

Or run `python scripts/check_limits.py`. Value `0` means unlimited; any non-zero is enforced. Exceeding either limit on `POST /workloads/`, `PATCH /workloads/{id}/settings/`, or autoscaling `maxCount` returns **HTTP 403** with body `{"detail": "Requested replicas (N) exceeds the maximum allowed (M)."}`. Both fields were added in spec v2.46.

## Public-spec path-key prefix quirk

The published spec at `https://docs.datarobot.com/en/docs/api/reference/public-api/openapi.yaml` aggregates multiple internal specs and is internally inconsistent about path-key prefixing. Runtime URLs are unaffected because `${DATAROBOT_ENDPOINT}` already includes `/api/v2`, but **spec lookups** need to know:

| Path namespace | Keyed in spec as | Example |
|---|---|---|
| Workloads + artifacts | **with** `/api/v2/` | `/api/v2/workloads/{workload_id}/protons/{proton_id}/statusDetails` |
| OTEL (workload telemetry) | **with** `/api/v2/`, and **templated** | `/api/v2/otel/{entityType}/{entityId}/logs/` (`{entityType}` = literal `workload`) |
| Credentials | **with** `/api/v2/` | `/api/v2/credentials/` |
| Compute bundles | **with** `/api/v2/` | `/api/v2/mlops/compute/bundles/` |

When grepping `spec["paths"]`, try both shapes if the first miss. Runtime calls are always `${DATAROBOT_ENDPOINT}/<rest of path>` regardless.

## Credential types and `key` field names

Used in `environmentVars` entries shaped as `{"source": "dr-credential", "name": "<env var>", "drCredentialId": "<id>", "key": "<key below>"}`. This table aggregates fields the agent would otherwise have to look up by grepping each `*Credentials` schema individually.

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

For any credential type not listed: fetch the spec and look up `<Type>Credentials` (e.g. `S3Credentials`, `BasicCredentials`, `OAuthCredentials`) — the schema's properties are the valid `key` values.

## Sharing — role values are UPPERCASE, not the lowercase the docs show

`PATCH /workloads/{id}/sharedRoles` (and the equivalent GET) uses roles from the
wider platform sharing enum. The Sharing and access control docs give lowercase
examples (`owner`, `user`, `consumer`); the API itself rejects those with
**`422`** and lists the accepted values in the error body: `OWNER`, `USER`,
`CONSUMER` (uppercase). Use uppercase.

The call **replaces the entire role list** — it's not a delta/merge. Read the
current roles first, include the owner (and anyone else who should keep
access) in the PATCH body, or they lose access.

## Schemas where the read model and write model diverge

The spec defines these but the naming/divergence is non-obvious:

- **Artifacts:** the read body is `ArtifactFormatted`; the PATCH write body is `UpdateArtifactRequest` and **does NOT accept `spec.type`** (that's a read-only discriminator). The `MultiContainerArtifactSpec` schema covers the `spec` object both ways.
- **Artifact creation:** there is **no** `CreateArtifactRequest` schema. Artifacts are created either inline via `CreateWorkloadRequest.artifact`, or by cloning via `ArtifactCloneRequest` (note the word order — not `CloneArtifactRequest`).
- **Replacement:** `POST` body is `StartReplacementRequest`; the optional `config` block is `ReplacementConfig`. Only `strategy: "rolling"` is supported.
- **Image builds:** read body is `ImageBuildFormatted`; build config on the artifact is `ImageBuildConfig`. Success status can be either `BUILT` or `COMPLETED` depending on platform version — treat both as terminal-success.
