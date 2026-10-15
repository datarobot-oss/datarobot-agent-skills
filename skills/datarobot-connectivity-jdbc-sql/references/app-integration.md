# Application integration

Call `/jdbcDataPreview/` and `/jdbcExecution/` from Python services and DataRobot custom applications, restore column types, and fix the JDBC path in Talk to My Data.

## Contents

- [Client choice](#client-choice)
- [Minimal client](#minimal-client)
- [Restoring types](#restoring-types)
- [Errors and retries](#errors-and-retries)
- [Writes and API keys](#writes-and-api-keys)
- [Talk to My Data](#talk-to-my-data)

## Client choice

Call the REST routes directly with `requests` or `httpx`. The `datarobot` SDK hides route and retry behavior:

| SDK | `JdbcPreview.preview` | `JdbcPreview.execute_update` |
|---|---|---|
| 3.14–3.18 | Posts to `/jdbcDataPreview/`; 60 s read timeout; no bind parameters | Not available |
| 3.19 | Posts to `/jdbcPreviewQuery/`. Can return 403 on accounts without the "Enable the Future Public API" feature, and app-scoped API keys may be refused; `read_timeout=300` | Posts to `/jdbcExecution/`; `read_timeout=60` |

If you use the SDK anyway:

- The default client retries POSTs on 413, 429, 502, 503, and 504 (up to about 11 attempts), so a retried `/jdbcExecution/` can run DML twice. `dr.Client(max_retries=0)` turns those retries off, but the client still retries connection resets. Use raw HTTP for writes.
- `dr.Client().post(...)` camelCases nested dict keys: `private_key_base64` becomes `privateKeyBase64`. Wrap `parameters` in `datarobot.utils.rawdict`. The `JdbcPreview` methods already do this.
- `JdbcPreviewData.df` loses precision: TIME becomes `None`, DECIMAL becomes float, integer columns with NULLs become float64. Restore types yourself.

## Minimal client

```python
from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

ENDPOINT = os.environ["DATAROBOT_ENDPOINT"].rstrip("/")  # ends in /api/v2
TOKEN = os.environ["DATAROBOT_API_TOKEN"]

class JdbcSqlError(Exception):
    def __init__(self, status: int, message: str, errors: dict[str, Any] | None = None) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status, self.message, self.errors = status, message, errors or {}

    @property
    def is_sql_error(self) -> bool:  # preview format; False means URL, driver, or network problem
        return self.status == 400 and self.message.startswith("SQL [")

def as_properties(raw: dict[str, Any] | None) -> dict[str, str]:  # true -> "true", 10 -> "10"
    return {k: v if isinstance(v, str) else json.dumps(v) for k, v in (raw or {}).items() if v is not None}

def _post(route: str, body: dict[str, Any], read_timeout: float) -> dict[str, Any]:
    resp = requests.post(
        f"{ENDPOINT}/{route}/", json={k: v for k, v in body.items() if v is not None},
        headers={"Authorization": f"Bearer {TOKEN}"}, timeout=(10, read_timeout),
    )
    try:
        payload: dict[str, Any] = resp.json()
    except ValueError:  # a 401 can have an empty body
        payload = {}
    if resp.status_code != 200:
        raise JdbcSqlError(resp.status_code, payload.get("message") or resp.text, payload.get("errors"))
    return payload

def preview(jdbc_url: str, sql: str, parameters: dict[str, str], max_rows: int = 1000,
            bind_params: list[Any] | None = None) -> dict[str, Any]:
    text = sql.strip()
    while text.endswith(";"):  # the wrapper rejects a trailing ;
        text = text[:-1].rstrip()
    body = {"jdbcUrl": jdbc_url, "sql": text + "\n",  # the newline ends a trailing -- comment
            "maxRows": max_rows, "parameters": parameters, "bindParams": bind_params}
    for delay in (2, 4, 8, None):  # reads only: back off on 429
        try:
            return _post("jdbcDataPreview", body, read_timeout=310)  # server deadline: 300 s
        except JdbcSqlError as exc:
            if exc.status != 429 or delay is None:
                raise
            time.sleep(delay)
    raise AssertionError("unreachable")

def execute(jdbc_url: str, sql: str, parameters: dict[str, str], bind_params: list[Any] | None = None) -> None:
    """One statement, one attempt. On any failure, read the target state before re-running."""
    body = {"jdbcUrl": jdbc_url, "sql": sql, "parameters": parameters, "bindParams": bind_params}
    message = _post("jdbcExecution", body, read_timeout=40).get("message")  # server deadline: 30 s
    if message != "OK":  # a 200 can carry another message
        raise JdbcSqlError(200, str(message))
```

Check every preview for truncation: if `len(result["records"]) == max_rows`, warn the user or tighten the query.

## Restoring types

Cells are strings or `null`. Map `resultSchema[i].dataTypeInt` (`java.sql.Types`); fall back to the `dataType` name when `dataTypeInt` is missing.

| `dataTypeInt` | JDBC types | Python value | pandas dtype |
|---|---|---|---|
| -7, 16 | BIT, BOOLEAN | `bool` (`"True"`/`"False"`) | `boolean` |
| -6, 5, 4, -5 | TINYINT, SMALLINT, INTEGER, BIGINT | `int` | `Int64` |
| 6, 7, 8 | FLOAT, REAL, DOUBLE | `float` | `float64` |
| 2, 3 | NUMERIC, DECIMAL | `Decimal`, or keep the string | `object` |
| 1, 12, -1, -9, -15, -16 | CHAR, VARCHAR, LONGVARCHAR, NVARCHAR, NCHAR, LONGNVARCHAR | `str` | `string` |
| 91, 92 | DATE, TIME | `date`, `time` | `object` |
| 93, 2014 | TIMESTAMP, TIMESTAMP_WITH_TIMEZONE | `datetime` in UTC | `datetime64[us, UTC]` |
| -2, -3, -4 | BINARY, VARBINARY, LONGVARBINARY | `bytes` from hex | `object` |
| Anything else | — | `str` | `string` |

```python
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pandas as pd  # pandas >= 2.0

BOOL, INT, FLOAT, DECIMAL = {-7, 16}, {-6, 5, 4, -5}, {6, 7, 8}, {2, 3}
DATE, TIME, TIMESTAMP, BINARY, VARCHAR = 91, 92, {93, 2014}, {-2, -3, -4}, 12
NAME_PREFIXES = (  # fallback when dataTypeInt is missing; longer prefixes first
    ("INTERVAL", VARCHAR), ("TIMESTAMP", 93), ("DATETIME", 93), ("DATE", DATE), ("TIME", TIME),
    ("BOOL", 16), ("BIT", -7), ("BIGINT", -5), ("SMALLINT", 5), ("TINYINT", -6), ("INT", 4),
    ("DOUBLE", 8), ("FLOAT", 8), ("REAL", 7), ("DEC", 3), ("NUMERIC", 2), ("NUMBER", 2),
)
CONVERTERS: dict[int, Callable[[str], Any]] = {  # anything not listed: str
    **dict.fromkeys(BOOL, lambda s: s == "True"), **dict.fromkeys(INT, int),
    **dict.fromkeys(FLOAT, float), **dict.fromkeys(DECIMAL, Decimal), **dict.fromkeys(BINARY, bytes.fromhex),
    **dict.fromkeys(TIMESTAMP, lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)),
    DATE: lambda s: dt.date.fromisoformat(s[:10]), TIME: dt.time.fromisoformat,
}
PANDAS_DTYPES = {  # anything not listed: "string"
    **dict.fromkeys(BOOL, "boolean"), **dict.fromkeys(INT, "Int64"), **dict.fromkeys(FLOAT, "float64"),
    **dict.fromkeys(TIMESTAMP, "datetime64[us, UTC]"), **dict.fromkeys(DECIMAL | BINARY | {DATE, TIME}, "object"),
}

def type_code(entry: dict[str, Any]) -> int:
    if entry.get("dataTypeInt") is not None:
        return int(entry["dataTypeInt"])
    name = str(entry.get("dataType", "")).upper()
    return next((code for prefix, code in NAME_PREFIXES if name.startswith(prefix)), VARCHAR)

def to_pandas(result: dict[str, Any]) -> pd.DataFrame:
    schema, series = result.get("resultSchema") or [], {}
    for i in range(len(result["columns"])):
        code = type_code(schema[i]) if i < len(schema) else VARCHAR
        convert = CONVERTERS.get(code, str)
        values = [None if row[i] is None else convert(row[i]) for row in result["records"]]
        series[i] = pd.Series(values, dtype=PANDAS_DTYPES.get(code, "string"))
    frame = pd.DataFrame(series)
    frame.columns = result["columns"]  # positional, so duplicate names survive
    return frame
```

## Errors and retries

Full table: `api-reference.md`, Errors. Map responses to app behavior:

- 400 starting with `SQL [` (preview format): show the database error and let the user or the LLM fix the query.
- Any other 400 (bad URL prefix, unreachable host, `Internal error`), 401 (DataRobot token), 403 with `Details:` (database login or privilege), 404 (needs API 2.43 for preview, 2.45 for execute): configuration errors. Report them; rewriting the SQL won't help.
- 408: make the query cheaper. Never re-run an execute call blindly.
- 413 or 422: fix the request body (`errors` names the field).
- 429: back off and retry, reads only.

## Writes and API keys

- The app-scoped API key of a DataRobot custom application can call `/jdbcDataPreview/`, but `/jdbcExecution/` may be refused (`jdbc_sql.py routes` with that key shows it). Use a user API key for writes, or keep the app read-only. Never let an app send generated SQL to `/jdbcExecution/` by itself.
- Send one statement per call, with no retry layer. Prefer idempotent statements (`MERGE`, `INSERT … WHERE NOT EXISTS`) so a deliberate re-run is safe.
- After a 408, a dropped connection, or a client timeout, read the target state with a preview before deciding to re-run. Warm cold warehouses (Snowflake, Databricks) with a preview before the first execute call.
- Load `parameters` from a secret store or environment variables, and never log request bodies.

## Talk to My Data

Applies to the public `datarobot-community/talk-to-my-data-agent` template, v11.13.1. Its `database` connection type reads `DATABASE_CONNECTION_TYPE=datarobot_jdbc` (legacy `snowflake`, `sap`, `bigquery`, and `databricks` use the same operator), `JDBC_URI`, and an optional JSON object in `JDBC_CONNECTION_PARAMETERS`. `JdbcPreviewOperator` calls SDK `JdbcPreview.preview` through `loop.run_in_executor`. The SDK version is not pinned: `core/pyproject.toml` sets only `datarobot>=3.16.0`, the lockfiles resolve 3.17 and 3.18, and the platform installs dependencies at deploy time. Fix list:

1. **Pin the route.** SDK 3.19 `JdbcPreview.preview` posts to `/jdbcPreviewQuery/`, which can be feature-gated and may refuse app-scoped API keys. Post to `jdbcDataPreview/` explicitly through `dr.client.get_client()`. To see which routes a key can use, run `jdbc_sql.py routes` with that key as `DATAROBOT_API_TOKEN`.
2. **Restore types.** `execute_query` builds non-empty results without types, so every column is a string. Map `resultSchema` as in [Restoring types](#restoring-types); `to_polars` below does it for polars. Don't reuse `BaseRecipe.convert_preview_to_dataframe`: it turns NULL booleans into `False`, silently nulls values that fail to cast, and maps BIGINT to `Decimal`.
3. **Cap rows.** Every query requests 10,000 rows and truncates silently. Have the generated SQL aggregate or `LIMIT`, send a smaller `maxRows`, and log a warning when `len(records) == maxRows`. The result metadata has no warning field; add one to show truncation in the UI.
4. **Timeouts.** The `timeout` argument is ignored, and SDK 3.18 reads with a 60 s timeout. Use at least 300 s for queries, but keep `validate_connection` short: infra calls it synchronously during `pulumi up` (`infra/infra/components/dr_credential.py`). Run previews on a dedicated thread pool; the default executor is shared with DuckDB work.
5. **Use the requesting user's token.** `use_user_token` calls `dr.Client(...)`, which sets a context-local client and a process-wide fallback. A `run_in_executor` worker thread doesn't inherit context variables, so `get_client()` there returns the fallback, which a concurrent request from another user may have replaced. Run the call through `contextvars.copy_context().run`, or use `asyncio.to_thread`, which copies the context.
6. **Keep property names.** When posting through the SDK client, wrap `parameters` in `rawdict` so keys like `private_key_base64` survive, and send string values.
7. **Stay read-only.** Keep `validate_read_only`, use a read-only database login, and never route generated SQL to `/jdbcExecution/` (app-scoped keys may be refused anyway).
8. **Trailing `;` and comments.** `validate_read_only` tolerates a trailing `;`, but `execute_query` posts the original string, and the wrapper rejects a `;` even on its own line. The prompts also ask the LLM to comment its code, and a trailing `-- comment` swallows the wrapper's closing parenthesis. Strip the `;` and end the SQL with a newline. On PostgreSQL, `SELECT 1 AS ok -- note` fails with `syntax error at end of input`, and the same SQL followed by a newline runs.
9. **SQL Server.** The wrapper rejects CTEs, `ORDER BY` without `TOP`, and unnamed or duplicate columns, while `validate_read_only` allows `WITH`. Add these rules to the SQL Server system prompt.
10. **Connection check.** `validate_connection` sends a bare `SELECT 1`, which fails on SAP HANA and Datasphere (needs `FROM DUMMY`) and on SQL Server (unnamed column). Send `SELECT 1 AS ok`, or `SELECT 1 AS ok FROM DUMMY` for `jdbc:sap:`.
11. **Fail fast on configuration errors.** `classify_db_failure` treats every 400 as fixable SQL, so `The connection attempt failed.` re-prompts the LLM up to the reflection limit. Raise `DatabaseFailure` for a 400 that doesn't start with `SQL [`, a 404, or a 422. Also add `except DatabaseFailure: raise` before `except Exception` in `_run_database_analysis` (`core/src/core/api.py`): that handler otherwise wraps it as retryable again.
12. **Tests.** `core/tests/test_jdbc_preview_operator.py` and `test_get_database_operator.py` patch `database_implementations.JdbcPreview` and assert the old request (`max_rows=10_000`, `sql="SELECT 1"`). Update them with the operator, and add a test that a `DatabaseFailure` stops after one attempt.
13. **More dialects.** The URL prefix picks the dialect. `JDBCCredentials` accepts `postgresql`, `mysql`, `sqlserver`, `snowflake`, `sap`, `bigquery`, `databricks`, and `redshift` (including `redshift:iam`). To add `jdbc:trino:`, extend that prefix list, `_dialect_key`, identifier quoting, the table-discovery query, and the system prompts.

Out of scope for the migration, but worth knowing: PostgreSQL discovery lists only `BASE TABLE`s in `public`, and `get_data` selects unqualified table names, so widening discovery also needs qualified names.

Migration sketch for `JdbcPreviewOperator.execute_query` (fixes 1–6, 8, and the raise from 11), on top of the module's existing imports and the [Restoring types](#restoring-types) helpers:

```python
import contextvars
import functools
import json
from concurrent.futures import ThreadPoolExecutor

from datarobot.client import get_client
from datarobot.errors import ClientError
from datarobot.utils import rawdict

PREVIEW_MAX_ROWS = 1_000  # was 10_000; generated SQL should aggregate or LIMIT
JDBC_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="jdbc-preview")
POLARS_TYPES = {
    **dict.fromkeys(BOOL, pl.Boolean), **dict.fromkeys(INT, pl.Int64), **dict.fromkeys(FLOAT | DECIMAL, pl.Float64),
    DATE: pl.Date, TIME: pl.Time, **dict.fromkeys(TIMESTAMP, pl.Datetime("us", "UTC")),
}
POLARS_CONVERTERS = {**CONVERTERS, **dict.fromkeys(DECIMAL, float), **dict.fromkeys(BINARY, str)}  # hex stays text

def to_polars(result: dict[str, Any]) -> pl.DataFrame:
    """Typed columns; NULL stays null, and a column whose cells don't parse stays text."""
    schema, columns, seen = result.get("resultSchema") or [], [], {}
    for i, name in enumerate(result["columns"]):
        seen[name] = seen.get(name, 0) + 1
        label = name if seen[name] == 1 else f"{name}_{seen[name]}"  # polars needs unique names
        code = type_code(schema[i]) if i < len(schema) else VARCHAR
        cells = [row[i] for row in result["records"]]
        convert = POLARS_CONVERTERS.get(code, str)
        try:
            values = [None if c is None else convert(c) for c in cells]
            columns.append(pl.Series(label, values, dtype=POLARS_TYPES.get(code, pl.String), strict=True))
        except (ValueError, TypeError, OverflowError, pl.exceptions.PolarsError):
            columns.append(pl.Series(label, cells, dtype=pl.String))
    return pl.DataFrame(columns)

def _jdbc_preview(jdbc_url: str, sql: str, raw: dict[str, Any] | None, max_rows: int, read_timeout: float) -> dict[str, Any]:
    client = get_client()  # the requesting user's client, thanks to copy_context below
    params = {k: v if isinstance(v, str) else json.dumps(v) for k, v in (raw or {}).items() if v is not None}
    text = sql.strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    body = {"jdbcUrl": jdbc_url, "sql": text + "\n",  # the newline ends a trailing -- comment
            "maxRows": max_rows, "parameters": rawdict(params)}
    return client.post("jdbcDataPreview/", json=body, timeout=(client.connect_timeout, read_timeout)).json()

class JdbcPreviewOperator(DatabaseOperator[JDBCCredentials]):  # existing class; replace execute_query
    async def execute_query(self, query: str, timeout: int | None = None) -> pl.DataFrame:
        creds = self._credentials
        read_timeout = min(timeout or 300, 300) + 10  # server deadline: 300 s
        call = functools.partial(contextvars.copy_context().run, _jdbc_preview, creds.jdbc_uri, query,
                                 creds.jdbc_connection_parameters, PREVIEW_MAX_ROWS, read_timeout)
        try:
            result = await asyncio.get_running_loop().run_in_executor(JDBC_POOL, call)
        except ClientError as e:
            sql_error = e.status_code == 400 and str(e.json.get("message", "")).startswith("SQL [")
            if e.status_code in (400, 404, 422) and not sql_error:  # URL, driver, network, old DataRobot
                raise DatabaseFailure(OUTAGE_MESSAGE, code=query, exception=e) from e
            raise InvalidGeneratedCode(f"JDBC query failed: {e}", code=query, exception=e) from e
        except Exception as e:  # timeouts, 5xx, transport errors: classify_db_failure maps them
            raise InvalidGeneratedCode(f"JDBC query failed: {e}", code=query, exception=e) from e
        if len(result["records"]) >= PREVIEW_MAX_ROWS:
            logger.warning("JDBC result truncated at %d rows", PREVIEW_MAX_ROWS)
        return to_polars(result)
```

In `_run_database_analysis`, let the failure through before the generic handler:

```python
    try:
        ...  # existing analysis
    except DatabaseFailure:
        raise
    except Exception as e:  # existing handler
        ...
```

Keep the other TTMD sources off these routes:

- DataRobot data-connection sources (`external_data_store_*`): PostgreSQL, Redshift, and Databricks through Spark SQL recipes; MySQL and Impala through `externalDataStores/{id}/verifySQL/`. TTMD already holds the datastore ID and its default credential ID, so use `POST /externalDataStores/{id}/previewQuery/` (skill `datarobot-connectivity-datastore-sql`). The JDBC routes need plaintext secrets, and DataRobot never returns stored ones.
- Data Registry datasets (`remote_catalog`, Spark wrangling recipes) have no JDBC URL. Keep them on recipes.
