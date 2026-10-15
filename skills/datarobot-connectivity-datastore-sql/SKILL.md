---
name: datarobot-connectivity-datastore-sql
description: >-
  Query, explore, and update databases through existing DataRobot data
  connections (datastores) with the connection's stored credentials: no
  connection strings, no app scaffolding. Use when the user wants to list
  DataRobot data connections, browse schemas, tables, or columns, preview a
  table, or run a SQL SELECT against any database connected in DataRobot; or
  run INSERT/UPDATE/DELETE/MERGE/CREATE (DML/DDL) through a Snowflake,
  Databricks, BigQuery, SAP Datasphere, or Trino connection. Examples: "query
  my Snowflake data connection", "show 10 rows from SALES.ORDERS in datastore
  <id>", "insert yesterday's totals into daily_summary in my Databricks
  connection". With only a JDBC URL and credentials, use
  datarobot-connectivity-jdbc-sql. Creating a connection happens in the
  DataRobot UI.
---

# DataRobot Datastore SQL

Run SQL through a data connection the user already set up in DataRobot; the API calls it a datastore. DataRobot resolves the connection and its stored credential server-side, so no database secrets pass through the agent.

For a JDBC URL and credentials instead of a DataRobot connection, use `datarobot-connectivity-jdbc-sql`.

## Prerequisites

- **Auth:** set both `DATAROBOT_ENDPOINT` (ends in `/api/v2`) and `DATAROBOT_API_TOKEN`, or neither, in which case both come from `~/.config/datarobot/drconfig.yaml`. If auth fails, invoke `datarobot-setup`.
- **Python 3.9+, standard library only.** Run the script by its path in this skill's folder: `python3 <skill-dir>/scripts/datastore_sql.py`.

## Script

`datastore_sql.py <command> -h` lists every option.

| Command | Purpose |
|---|---|
| `datastores [--name TEXT]` | Every connection you can access. `role` is your access (OWNER, EDITOR, CONSUMER). `sql` is what DataRobot supports for the driver (`read (fast) + write`, `read (fast)`, `read (legacy)`, `no SQL (file/object connector)`); it is the write gate, not a grants check |
| `credentials --datastore-id ID` | Your stored credentials for the connection, with the default marked |
| `routes --datastore-id ID` | Whether your account can use the newer read and write routes, and whether this connection's driver can write. Sends no SQL |
| `schemas` · `tables [--schema S --like TEXT]` · `columns --table T` | Discovery. `--like` matches part of the name, any case |
| `preview --table T [--schema S]` | First rows of a table (default `--max-rows 20`) |
| `query --sql "…" \| --sql-file F [--bind '[42, "a"]']` | One read-only statement (default `--max-rows 100`, max 10000). Binds fill `?` placeholders in order |
| `plan --sql "…" \| --sql-file F [--bind …]` | DML/DDL plan and confirm token. Changes nothing |
| `execute <same arguments> --confirm TOKEN` | Runs the approved plan |

Commands that act on one connection take `--datastore-id` and an optional `--credential-id`. Without `--credential-id`, the connection's default credential is used.

Output options:

- `--format table|csv|json`: CSV sends the `#` notes to stderr.
- `--show N`: rows printed, default 20 for `preview` and `query`, 100 for listings.
- `--width N`: cell width.
- `--out FILE`: saves every fetched row (JSON for `.json`, else CSV); stdout then shows only a preview.

Exit codes: 0 ok · 1 usage · 2 API error, or a write whose outcome is unknown · 3 the confirm token no longer matches · 4 the database reported a write failure · 5 not possible here (route unavailable, or the connection cannot write).

## Workflow

```
- [ ] 1. Find the connection: `datastores --name <text>`
- [ ] 2. Discover: `tables --schema <s> --like <text>`, `columns --table <t>`
- [ ] 3. Read: `preview`, or `query` with WHERE/LIMIT/aggregation
- [ ] 4. Write, only if the user asked: checks → `plan` → approval → `execute --confirm` → verify
```

- **Several matches:** prefer the exact name the user gave. When the user says "my", prefer a connection with role OWNER. If it is still ambiguous, ask.
- **No match:** run `datastores` without `--name`. A `no SQL` connection is a file or object store and cannot be queried.
- **Credentials:** run `credentials` to see which credential will be used, or when the user names another one.
- **Names:** Datasphere spaces and BigQuery datasets are schemas. In SQL, quote names that are mixed-case, start with a digit, or contain special characters. Use `"…"` for Snowflake, Datasphere/HANA, Postgres, Trino and Oracle, and `` `…` `` for MySQL, BigQuery and Databricks. See `references/connector-support.md`.
- **Wide tables:** select the columns you need with `query`, or save with `--out` and summarize the file.
- **Empty discovery:** discovery shows only objects the credential can access. Check the schema name, its case, and the grants.

**Writes:**

1. **Check write support.** The connection's `sql` must be `read (fast) + write`; `plan` refuses others (exit 5). If it isn't, stop: DataRobot cannot write there. Offer `datarobot-connectivity-jdbc-sql` with the database's own JDBC URL.
2. **Check the target and impact.** Confirm the target exists and is a table, not a view (`tables`, `columns`). If it doesn't, stop and ask the user. Measure the impact with a read: `SELECT COUNT(*) FROM t WHERE <same condition>` for UPDATE or DELETE; required columns and existing keys for INSERT.
3. **Plan.** `plan --datastore-id <id> --sql "<sql>"` prints `WRITE PLAN (nothing has run)` and a token. It only reads connection metadata. Show the plan to the user and ask for an explicit yes.
4. **Execute.** Run `execute` with the same arguments plus `--confirm <token>`. The token covers the connection, credential, SQL and binds. Any change means a new plan and a new approval (exit 3).
5. **Verify.** No row count comes back, so check with `query` for DML or `tables`/`columns` for DDL.

Several statements in one request:

- **Snowflake** runs them in one transaction.
- **Databricks** runs them without one, so earlier statements stay applied if a later one fails.
- **Other connectors:** send one statement per `execute`.

## Rules

- **Never** pass `--confirm` until the user has approved that exact plan.
- **Never** retry a write after exit 2 until a read shows its effect: the outcome is unknown.
- Writes run with your credential for the connection, and anyone with access to it can write, even a CONSUMER. State the target and impact plainly.
- `query` and `preview` run only reads (SELECT, WITH, VALUES, SHOW, DESCRIBE, EXPLAIN). The check cannot see side effects of functions a query calls, so prefer a read-only credential for exploration.
- Keep results small: aggregate, filter, LIMIT. Save large results with `--out`.
- Tell the user which route answered: `preview` and `query` print a `# route:` line. `verifySQL (legacy)` results have no column types and stop at 999 rows.

## Routes

The script picks the route and falls back by itself. Details are in `references/api-reference.md`.

| Route (`POST /externalDataStores/{id}/…/`) | Use | If unavailable |
|---|---|---|
| `previewQuery/` | Read SQL, typed results, bind parameters | Falls back to `verifySQL/` (≤999 rows, no types) |
| `preview/` | Table sample | Falls back to `verifySQL/` with `SELECT * FROM <table>` |
| `executeUpdate/` | DML/DDL | No fallback. A 403 `… (Enable the Future Public API)` means writes are not enabled for the account: ask a DataRobot admin, or use the JDBC skill |

`routes` shows which of these the account can use. Discovery commands use separate metadata endpoints and print no `# route:` line.

## Common errors

| Error | Fix |
|---|---|
| 422 `Credentials were not provided…` | Pass `--credential-id` or set a default. A wrong connection id causes the same error, so verify it with `datastores` |
| 403 `You do not have the required permissions. Details: …` | The database rejected the stored login or a privilege; fix the credential or the grants |
| 400 with a database message | A missing object, identifier case or quoting, or the dialect; check `tables`/`columns` |
| 408 `Request timed out` | Reads: a warehouse is still starting or the query is heavy (300 s limit); retry later or narrow the query. Writes: the outcome is unknown; check with `query` |

Full table: `references/troubleshooting.md`.

## Using DataRobot SDK

The script calls REST directly. That avoids SDK client retries, which could run a write twice. In application code, `datarobot>=3.19` wraps the same routes:

```python
import datarobot as dr

store = dr.DataStore.get("<data-store-id>")
rows = store.preview_query("SELECT region, COUNT(*) AS n FROM sales.orders GROUP BY region", max_rows=100)
message = store.execute_update("UPDATE t SET flag = TRUE WHERE id = ?", bind_parameters=[42])  # "OK" on success
```

Raw REST, fallback logic, and SDK caveats are in `references/api-reference.md`.

## References

- `references/api-reference.md`: routes, bodies, responses, value formatting, limits, bind parameters, timeouts, discovery routes, app-code snippets
- `references/connector-support.md`: capability and transactions by connector, dialects and quoting, DDL differences, discovery SQL
- `references/troubleshooting.md`: every known error, its cause, and the fix

## Related skills

- `datarobot-connectivity-jdbc-sql`: SQL through a caller-supplied JDBC URL; also writes where a DataRobot connection cannot
- `datarobot-setup`: authentication and SDK setup
- `datarobot-data-preparation`: register data as a DataRobot dataset for modeling
