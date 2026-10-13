# Datastore SQL routes: API reference

Request and response contract for running SQL through a DataRobot data connection, for direct REST calls and app code.

**Contents:** Routes · Availability · Request bodies · Responses · Values and NULLs · Row limits · Bind parameters · Timeouts and retries · Discovery routes · Calling from app code

## Routes

All routes are `POST {DATAROBOT_ENDPOINT}/externalDataStores/{dataStoreId}/<route>/` with `Authorization: Bearer <DATAROBOT_API_TOKEN>` and a JSON body. Keep the trailing slash.

| Route | Purpose | Notes |
|---|---|---|
| `previewQuery/` | One read query | Newer route; typed results; bind parameters |
| `preview/` | Rows of one table | Newer route; no SQL needed |
| `executeUpdate/` | DML/DDL | Newer route; returns a status message only |
| `verifySQL/` | One read query | Legacy route, documented publicly; no types, no binds, ≤999 rows |

## Availability

The newer routes are public but not in the published API reference. Check the status and message to decide what to do:

| Response | Meaning | What to do |
|---|---|---|
| 403 `You do not have access to this functionality (Enable the Future Public API).` | The newer routes are not enabled for this account | Reads: use `verifySQL/` (the script falls back automatically). Writes: ask a DataRobot admin, or use `datarobot-connectivity-jdbc-sql` with the database's own JDBC URL |
| 403 `Access denied due to seat license restrictions` | The seat type excludes `previewQuery/` | Use `verifySQL/` |
| 404 `{"message": "Not Found"}` (exactly) | The route does not exist on this DataRobot version | Use `verifySQL/`; writes need a newer DataRobot |

Authorization checks run before body validation, so a 422 on an empty body proves the account can call the route.

## Request bodies

| Field | `previewQuery/` | `preview/` | `executeUpdate/` | `verifySQL/` |
|---|---|---|---|---|
| SQL | `sql` (required) | — | `sql` (required) | `query` (required) |
| `table` / `schema` / `catalog` | — | `table` required; others optional | — | — |
| `maxRows` | 0–10000, default 1000 | 0–10000, default 1000 | — | 0–999, **required** |
| `credentialId` | optional* | optional* | optional* | **required** |
| `bindParams` | optional | — | optional | — |

\* When omitted, DataRobot uses the user's **default credential** for the connection. Without one: 422 `Credentials were not provided and default credentials were not found.` That check runs before the connection lookup, so the same 422 appears for a wrong `dataStoreId`.

```json
POST .../externalDataStores/<id>/previewQuery/
{"sql": "SELECT region, COUNT(*) AS n FROM sales.orders GROUP BY region", "maxRows": 100}

POST .../externalDataStores/<id>/executeUpdate/
{"sql": "INSERT INTO sales.audit (id, note) VALUES (?, ?)", "bindParams": [42, "backfill"]}
```

## Responses

`previewQuery/`, `preview/`:

```json
{"columns": ["id", "name", "active"],
 "records": [["1", "a", "True"], ["2", null, "False"]],
 "resultSchema": [{"name": "id", "dataType": "INTEGER", "precision": "10", "scale": "0", "dataTypeInt": 4}]}
```

- `resultSchema` can be `null`; `precision`/`scale` can be strings or integers. Parse leniently.
- `dataTypeInt` is the `java.sql.Types` code; use it to restore types.
- `verifySQL/` returns only `columns` and `records`.
- `executeUpdate/` returns `{"message": "OK"}`. **Treat only `"OK"` as success.** Another message can arrive with HTTP 200 and means the database reported a problem. No row count is returned: verify writes with a read.

## Values and NULLs

Cells are strings or `null`:

- NULL is JSON `null`.
- Booleans are `"True"`/`"False"`.
- Timestamps are ISO-8601 in UTC without an offset, e.g. `"2026-01-02T03:04:05"`.
- Binary values are upper-case hex.

Legacy-path connections (see `connector-support.md`) can format values differently.

## Row limits

- The SQL is sent unchanged. DataRobot stops reading at `maxRows`, but the database may still compute the full result. Put `LIMIT`, `WHERE`, or aggregation in the SQL.
- No truncation flag is returned. `len(records) == maxRows` means the result was probably cut.
- For column names and types only, query with `WHERE 1=0`.

## Bind parameters

- `bindParams` is a list of at most 100 values (string, number, boolean, null), bound in order to `?` placeholders.
- RFC 3339 strings such as `"2025-01-01T12:00:00Z"` are bound as timestamps.
- Binds work only on native-connector connections. Legacy-path connections silently drop them, so inline literals there.

## Timeouts and retries

- Each call has a 300 s server limit, after which you get 408 `Request timed out; try again later`. A stopped warehouse that is still starting (Databricks, Snowflake) can hit this on the first call.
- 429 means rate limited: back off and retry reads.
- **Never retry `executeUpdate/` automatically.** A timeout or dropped connection leaves the outcome unknown, so check with a read first.

## Discovery routes

| Call | Returns |
|---|---|
| `GET /externalDataStores/?type=all[&name=<text>]` | `{"data": [{id, canonicalName, type, driverClassType, role, …}]}`. **Without `type=all` only legacy JDBC connections are listed.** |
| `GET /credentials/associations/dataconnection:{id}/?orderBy=-isDefault` | `{"data": [{credentialId, name, credentialType, isDefault}]}` |
| `POST /externalDataStores/{id}/schemas/` `{credentialId}` | `{"catalogs": [...], "schemas": [...], "catalog": "<current>"}` |
| `POST /externalDataStores/{id}/tables/` `{credentialId, schema?, catalog?}` | `{"tables": [{name, type: TABLE\|VIEW, schema, catalog}]}` |
| `POST /externalDataStores/{id}/columns/` `{credentialId, table, schema?, catalog?}` | `{"columns": [{name, dataType, precision, scale}]}` |

The schema, table and column routes require an explicit `credentialId`, and they run on the slower legacy path.

## Calling from app code

Raw REST with a fallback for reads:

```python
import os
import requests

BASE = os.environ["DATAROBOT_ENDPOINT"].rstrip("/")
HEADERS = {"Authorization": f"Bearer {os.environ['DATAROBOT_API_TOKEN']}"}


def _route_unavailable(r: requests.Response) -> bool:
    try:
        message = str(r.json().get("message", ""))
    except ValueError:
        return False
    gated = "Future Public API" in message or "seat license" in message
    return (r.status_code == 403 and gated) or (
        r.status_code == 404 and message == "Not Found"
    )


def preview_query(ds_id: str, sql: str, credential_id: str, max_rows: int = 100) -> dict:
    url = f"{BASE}/externalDataStores/{ds_id}"
    body = {"sql": sql, "maxRows": max_rows, "credentialId": credential_id}
    r = requests.post(f"{url}/previewQuery/", headers=HEADERS, json=body, timeout=330)
    if _route_unavailable(r):
        legacy = {"query": sql, "maxRows": min(max_rows, 999), "credentialId": credential_id}
        r = requests.post(f"{url}/verifySQL/", headers=HEADERS, json=legacy, timeout=330)
    r.raise_for_status()
    return r.json()
```

The Python SDK (`datarobot>=3.19`) wraps the newer routes. Availability is the same as above:

```python
import datarobot as dr

store = dr.DataStore.get("<data-store-id>")
data = store.preview_query("SELECT 1 AS x", max_rows=10, credential_id="<id>")
print(data.columns, data.records, data.result_schema)
message = store.execute_update("DELETE FROM t WHERE id = ?", bind_parameters=[42])
assert dr.DataStore.is_execute_update_success(message)  # message == "OK"
```

SDK caveats:

- The default client retries POSTs on 413/429/502/503/504, so a write can run twice. `dr.Client(max_retries=0)` stops those retries, but the client still re-sends a request after a connection reset. Send writes with plain HTTP and no retry layer, as the bundled script does.
- `.df` loses precision: DECIMAL becomes float, TIME becomes None, and integer columns that contain NULL become float.
