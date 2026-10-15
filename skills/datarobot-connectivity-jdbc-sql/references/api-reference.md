# JDBC SQL REST API reference

Request, response, and error contract for running SQL through DataRobot against a caller-supplied JDBC URL.

## Contents

- [Routes](#routes)
- [Request body](#request-body)
- [Examples](#examples)
- [Preview response](#preview-response)
- [Execute response](#execute-response)
- [How the SQL runs](#how-the-sql-runs)
- [Limits and retries](#limits-and-retries)
- [Errors](#errors)
- [Bundled CLI](#bundled-cli)

## Routes

`POST`, JSON body, `Authorization: Bearer <DATAROBOT_API_TOKEN>`. `DATAROBOT_ENDPOINT` already ends in `/api/v2`. Always keep the trailing slash on the route.

| Route | Purpose | Since | App-scoped API key |
|---|---|---|---|
| `{DATAROBOT_ENDPOINT}/jdbcDataPreview/` | Run one read query, return rows | API 2.43 (DataRobot 11.7) | Allowed |
| `{DATAROBOT_ENDPOINT}/jdbcExecution/` | Run one DML or DDL statement | API 2.45 | App-scoped keys may be refused: use a user API key |

`bindParams` needs API 2.46. Some docs list two other names. Don't use them:

- `/jdbcPreviewQuery/`: a preview alias. On accounts without the "Enable the Future Public API" feature it can return 403 `{"message": "You do not have access to this functionality (Enable the Future Public API)."}`. App-scoped API keys of custom applications may be refused as well.
- `/jdbcExecuteUpdate/`: does not exist. 404 `{"message": "Not Found"}`.

`GET {DATAROBOT_ENDPOINT}/version/` returns the API version in `versionString`. A 404 `{"message": "Not Found"}` from a route means the installation predates it, or the path is wrong: check the spelling and the trailing slash.

To check the routes without running SQL, `scripts/jdbc_sql.py routes` posts `{"bindParams": []}` to `/jdbcDataPreview/`, `/jdbcExecution/`, and `/jdbcPreviewQuery/`. Validation rejects that body before anything runs:

| Response | Meaning |
|---|---|
| 422 `… is required` | Route available; bind parameters supported |
| 422 `bindParams is not allowed key` | Route available; bind parameters need API 2.46 |
| 404 `Not Found` | Route missing on this installation |
| 403 `… (Enable the Future Public API)` | Route gated for this account |
| Other 403 | Route refused for this API token, for example an app-scoped key |

## Request body

Keys are camelCase. Any other key (`jdbc_url`, `max_rows`, `credentialId`, …) returns 422 `"<key> is not allowed key"`.

| Field | Type | Route | Rules |
|---|---|---|---|
| `jdbcUrl` | string | both | Required, ≤ 16,384 chars. The URL prefix picks the driver; there is no driver field. See `jdbc-urls.md`. |
| `sql` | string | both | Required, ≤ 320,000 chars. One statement. |
| `maxRows` | integer | preview | 0–10,000, default 1,000. `/jdbcExecution/` rejects it with 422. |
| `parameters` | object | both | Optional. JDBC connection properties: `user`, `password`, `sslmode`, driver-specific keys. |
| `bindParams` | array | both | Optional, ≤ 100 items. Each item is a boolean, number, string, or `null`, bound in order to `?` placeholders. |

There is no stored-credential reference (no `credentialId`). Put secrets in `parameters` (preferred: keeps them out of URLs and logs) or in the URL.

### `parameters`: send strings

The server converts each value to text before the driver sees it:

| Sent | Driver receives |
|---|---|
| `true` / `false` | `"True"` / `"False"` |
| `null` | `"None"` on preview; dropped on execute |
| `{"a": 1}` | `"{'a': 1}"` |

Send every value as a JSON string, in the form the driver documents: `{"ssl": "true", "loginTimeout": "10"}`.

### `bindParams` coercion

| Sent | Bound as |
|---|---|
| Numeric-looking string (`"42"`, `"3.5"`) | Integer or float |
| `"YYYY-MM-DD"`, or RFC 3339 with an offset (`"2026-01-02T03:04:05+02:00"`) | Timestamp, converted to UTC |
| Integral float (`2.0`) | Integer |
| `null` | SQL `NULL` |
| `""` | Rejected with 422 |

To keep a numeric-looking string as text (zip code `"02134"`, IDs with leading zeros), inline it as a SQL literal (`WHERE zip = '02134'`) instead of binding it.

## Examples

Build the body with `jq` so secrets come from environment variables, not the command line:

```bash
jq -n '{jdbcUrl: env.JDBC_URL,
        sql: "SELECT id, name FROM public.users WHERE created_at > ?",
        maxRows: 100,
        parameters: {user: env.DB_USER, password: env.DB_PASSWORD},
        bindParams: ["2026-01-01"]}' |
  curl -sS -X POST "${DATAROBOT_ENDPOINT}/jdbcDataPreview/" \
    -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" \
    -H "Content-Type: application/json" --data-binary @-
```

```bash
jq -n '{jdbcUrl: env.JDBC_URL,
        sql: "UPDATE public.users SET active = ? WHERE id = ?",
        parameters: {user: env.DB_USER, password: env.DB_PASSWORD},
        bindParams: [false, 42]}' |
  curl -sS -X POST "${DATAROBOT_ENDPOINT}/jdbcExecution/" \
    -H "Authorization: Bearer ${DATAROBOT_API_TOKEN}" \
    -H "Content-Type: application/json" --data-binary @-
# {"message": "OK"}
```

## Preview response

HTTP 200. `resultSchema` has one entry per column; one is shown:

```json
{"columns": ["id", "name", "active", "score", "created"],
 "records": [["1", "alpha", "True", "1.5", "2026-01-02T03:04:05"],
             ["2", null, "False", "2.0", null]],
 "resultSchema": [{"name": "id", "dataType": "INTEGER", "precision": "10", "scale": "0", "dataTypeInt": 4}]}
```

- Every cell is a string or `null`. Restore types from `resultSchema`; `app-integration.md` has the mapping.
- `dataTypeInt` is the `java.sql.Types` code and `dataType` the type name. `precision` and `scale` are strings, so parse them leniently.
- A zero-row result still returns `columns` and `resultSchema`, with `"records": []`. For a schema-only call, add `WHERE 1=0` instead of sending `maxRows: 0`.
- The response has no row count and no truncation flag. If `len(records) == maxRows`, assume the result was truncated.

| Column type | Cell text |
|---|---|
| BOOLEAN, BIT | `"True"` / `"False"` |
| FLOAT, REAL, DOUBLE | Shortest round-trip form: `"2.0"`, `"1e-05"`, `"nan"` |
| DECIMAL, NUMERIC | The driver's `toString()` |
| DATE | `"YYYY-MM-DDT00:00:00"` |
| TIMESTAMP, TIMESTAMP WITH TIME ZONE | Converted to UTC, no offset; microseconds only when non-zero |
| TIME | `"HH:MM:SS"` |
| BINARY, VARBINARY | Upper-case hex |
| Geometry | WKT |
| JSON | Text |
| ARRAY | `"[1, 2]"` |

## Execute response

HTTP 200 `{"message": "OK"}`. No affected-row count. Treat only `"OK"` as success: a 200 can carry a different message.

## How the SQL runs

Preview wraps your SQL in a subquery aliased `_table` and adds the dialect's row limit. On PostgreSQL it runs `select * from (<your sql>) as "_table" fetch next <maxRows> rows only`; other dialects use their own row-limit form. Consequences:

- Send exactly one query, with no trailing `;`. The server rejects a trailing `;` even on its own line.
- A trailing line comment (`-- note`, MySQL `# note`) comments out the wrapper and fails with a syntax error. Drop it, or end the SQL with a newline: the server keeps the newline.
- `SHOW`, `DESCRIBE`, `EXPLAIN`, `CALL`, DML, and DDL fail. Query `information_schema` or catalog views instead (`jdbc-urls.md`, Discovery SQL).
- On SQL Server, every column needs a unique name, `ORDER BY` needs `TOP`, and CTEs (`WITH …`) fail. Alias expressions in every dialect (`COUNT(*) AS n`).
- `maxRows` limits the rows returned, not the work done: the database may still run the whole inner query. Add your own `WHERE` and `LIMIT`.
- Error positions (PostgreSQL `Position: 42`) count from the start of the wrapped SQL, not from your SQL.

Execute runs the SQL string as one driver `execute()` call with the driver's default autocommit:

- No statement splitting, no explicit transaction, no rollback.
- Several statements in one string work only where the driver allows it (MySQL `allowMultiQueries=true`, Snowflake `MULTI_STATEMENT_COUNT=0`), and even then they are not atomic. Send one statement per call.
- Verify the result with a preview query afterwards.

Each request opens a new database connection from DataRobot. The database must be reachable from DataRobot, not from your machine (`jdbc-urls.md`, Network reachability).

## Limits and retries

| Limit | Value | When exceeded |
|---|---|---|
| Preview deadline | 300 s | 408; the statement is cancelled |
| Execute deadline | 30 s, including connect and login | 408; the statement is cancelled |
| Concurrent requests | Set by the installation | 429 |
| Request body | 8 MB | 413 |

- Client read timeouts: at least 300 s for preview and 30 s for execute, plus a margin (for example 310 s and 40 s).
- Preview: retry 429 with exponential backoff. Retry 408 only after making the query cheaper or warming the warehouse.
- Execute: DataRobot never retries it, and clients must not retry it blindly either. After a 408, a 429, or a dropped connection, read the target state with a preview, then decide.
- Cold warehouses (Snowflake, Databricks) can use up the 30 s execute deadline while logging in. Warm them with a preview first and set low driver login timeouts (`jdbc-urls.md`, Timeouts).

## Errors

Error bodies are `{"message": "…"}`; 422 responses add `errors`. A 401 can have an empty body, so don't assume JSON.

| Case | HTTP | `message` |
|---|---|---|
| Validation | 422 | `Invalid field data`, with `errors` such as `{"maxRows": "value is greater than 10000"}`. Other texts: `is required`, `String is longer than 320000 characters`, `<key> is not allowed key` |
| Unsupported URL prefix (`jdbc:h2:`, `jdbc:db2:`) | 400 | `No suitable JDBC driver for the configured connection URL` |
| Bad database credentials or missing privilege | 403 | `You do not have the required permissions. Details: <driver message>`; a missing grant reads like `SQL [...]; ERROR: permission denied for schema <s>` |
| Host unreachable or connection refused | 400 | Driver message, such as `The connection attempt failed.` |
| SQL error (preview form shown) | 400 | `SQL [select * from (<your sql>) as "_table" fetch next N rows only]; <driver message>` (wrapper varies by dialect) |
| Deadline exceeded | 408 | `Request timed out; try again later` |
| Too many concurrent requests | 429 | Rate-limit message |
| Unclassified | 400 | `Internal error` |
| Missing or invalid DataRobot API token | 401 | May be empty |
| Route missing on older DataRobot | 404 | `Not Found`: preview needs API 2.43, execute 2.45 |

Triage:

- 400 starting with `SQL [` (verified for preview; execute errors may differ): the query is wrong. The brackets show the SQL as it ran; the tail is the database's error. Fix the query.
- Any other 400: URL, driver, or network problem. Rewriting the SQL won't help.
- 403 with `Details:` and a privilege error (`permission denied`, `permission was denied`, `command denied to user`, `insufficient privileges`): the login works but lacks a grant (USAGE on the schema, SELECT on the table). Ask the database owner for the grant, or use a login that has it.
- Any other 403 with `Details:`: the database rejected the login. Fix `parameters`, not the DataRobot token.
- 401: the DataRobot API token is missing or invalid.

## Bundled CLI

`scripts/jdbc_sql.py` wraps both routes:

```bash
python3 scripts/jdbc_sql.py routes                                           # which routes this DataRobot and token can use; no SQL
python3 scripts/jdbc_sql.py check
python3 scripts/jdbc_sql.py tables --schema <schema>
python3 scripts/jdbc_sql.py columns --table <table> --schema <schema>
python3 scripts/jdbc_sql.py query --sql "SELECT id, name FROM public.users" --max-rows 100 --format csv --out users.csv
python3 scripts/jdbc_sql.py plan --sql-file change.sql                       # prints the plan and a token; makes no API call
python3 scripts/jdbc_sql.py execute --sql-file change.sql --confirm <token>  # runs the approved plan
```

The URL comes from `--jdbc-url`, `--jdbc-url-env VAR`, or env `JDBC_URL` (then `JDBC_URI`). Properties come from `--param key=value`, `--param-env key=ENVVAR`, or the JSON in `--params-json-env VAR`. The JSON in `JDBC_CONNECTION_PARAMETERS` is read by default only with the URL from `JDBC_URL`/`JDBC_URI`, so one target's properties never go to another URL. `--bind '["2026-01-01", 42]'` sets `bindParams`. The token covers the URL, the properties, SQL, and binds. For a secret property it covers where the value comes from (`env DB_PASSWORD`), not the value: rotating a password in `.env` keeps the token, while switching to another variable changes it.
