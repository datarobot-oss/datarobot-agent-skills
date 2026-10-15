---
name: datarobot-connectivity-jdbc-sql
description: >-
  Run SQL against a database through DataRobot with a JDBC URL (or host, port,
  and database) and credentials you supply; no DataRobot data connection
  needed. Also use it to point an existing app such as Talk to My Data at
  DataRobot's low-latency /jdbcDataPreview/ route (/jdbcExecution/ only for
  user-approved writes). Use
  when the user wants to test a connection to PostgreSQL, MySQL, SQL Server,
  Snowflake, Databricks, Trino, SAP HANA or Datasphere, Redshift, or BigQuery,
  list tables or columns, run read queries, or run DML/DDL, e.g. "run this SQL
  on jdbc:postgresql://… through DataRobot". If the database is already a
  DataRobot data connection, use datarobot-connectivity-datastore-sql.
---

# DataRobot JDBC SQL

DataRobot opens a JDBC connection from its own network with the URL and driver properties you send. It runs one statement and returns the rows or a status. Nothing is registered in DataRobot.

If the database is already a DataRobot data connection, use `datarobot-connectivity-datastore-sql`: it uses the stored credential, so the agent never handles secrets.

## Prerequisites

- **Auth:** set both `DATAROBOT_ENDPOINT` (ends in `/api/v2`) and `DATAROBOT_API_TOKEN`, or neither, in which case both come from `~/.config/datarobot/drconfig.yaml`. An `--env-file` can also supply them. If auth fails, invoke `datarobot-setup`.
- **Python 3.9+, standard library only.** Run the script by its path in this skill's folder: `python3 <skill-dir>/scripts/jdbc_sql.py`. The `.env` stays in the user's project; pass its absolute path.
- **Network:** DataRobot itself opens the connection, so the database must be reachable from DataRobot: its cloud on SaaS, or the customer's cluster on self-managed installs. A database reachable only from the user's machine or private network, `localhost` included, will not work.

## Secrets stay out of the chat

- **Never ask the user to paste a password, token, or key into the chat, and never echo one.** Have the user put the values in a gitignored `.env`, editing it in their own editor:

  ```bash
  JDBC_URL=jdbc:postgresql://<host>:5432/<db>
  DB_USER=<user>
  DB_PASSWORD=<password>
  ```

- **If the user already pasted a secret,** don't repeat it. Ask the user to put it in `.env`, or write it there with a file edit; a shell command can leave it in logs. Recommend rotating it unless it is a published public credential.
- **Pass secrets as driver properties read from the environment:** `--env-file <path>/.env --param-env user=DB_USER --param-env password=DB_PASSWORD`. Non-secret values can use `--param key=value`. Prefer properties over credentials embedded in the URL.
- **`--env-file`** loads `KEY=VALUE` lines. It skips comments, strips quotes, never overrides variables that are already set, and can include DataRobot auth. Without `--jdbc-url`, the script reads `JDBC_URL` (or Talk to My Data's `JDBC_URI`) together with the JSON object in `JDBC_CONNECTION_PARAMETERS`. With an explicit URL it uses only the properties you pass.
- **Masking:** all output masks secrets. A plan names each secret's source, e.g. `*** (env DB_PASSWORD)`. The confirm token covers the source, not the value: rotating a password in `.env` needs no new approval, but switching to another variable does.

## Script

`jdbc_sql.py <command> -h` lists every option. Every command except `routes` takes the connection flags `--jdbc-url` or `--jdbc-url-env VAR`, `--param`, `--param-env`, `--params-json-env`, and `--env-file`.

| Command | Purpose |
|---|---|
| `check` | Connects and logs in (`SELECT 1`, or `SELECT 1 FROM DUMMY` on SAP). Does not check read access to tables |
| `tables [--catalog C --schema S --like TEXT]` | Tables and views, sorted (default `--max-rows 1000`). `--like` matches part of the name, any case |
| `columns --table T [--catalog C --schema S]` | Column names, types, and nullability, in table order |
| `query --sql "…" \| --sql-file F [--bind '[42, "a"]']` | One read-only query (default `--max-rows 100`, max 10000) |
| `plan --sql "…" \| --sql-file F [--bind …]` | DML/DDL plan and confirm token. Makes no API call |
| `execute <same arguments> --confirm TOKEN` | Runs the approved plan |
| `routes` | Which JDBC routes this DataRobot and API token can use, with bind support. Sends no SQL |

Output options:

- `--format table|csv|json`: CSV sends the `#` notes to stderr.
- `--show N`: rows printed, default 20 (100 for `tables` and `columns`).
- `--width N`: cell width.
- `--out FILE`: saves every fetched row (JSON for `.json`, else CSV); stdout then shows only a preview.

Exit codes: 0 ok · 1 usage · 2 API error, or a write whose outcome is unknown · 3 the confirm token no longer matches · 4 the database reported a write failure · 5 route unavailable (`routes` shows which).

## Workflow

```
- [ ] 1. URL and secrets in env/.env (never in chat); URL format from references/jdbc-urls.md
- [ ] 2. `check`: fix connectivity before anything else
- [ ] 3. Discover: `tables --schema <s> --like <text>`, `columns --table <t>`
- [ ] 4. Read: `query` with WHERE/LIMIT/aggregation
- [ ] 5. Write, only if the user asked: checks → `plan` → approval → `execute --confirm` → verify
```

**Empty discovery:** catalog views list only what the login can access. `tables` explains an empty result. On PostgreSQL, `tables` and `columns` show objects the login can't read, marked `readable=False`. A 403 `permission denied` means missing grants, not a wrong password.

**Writes:**

1. **Check connectivity.** `check` must pass for the target before you plan. If it fails, stop and resolve it with the user.
2. **Check the target and impact.** Confirm the target exists and is a table, not a view (`tables`, `columns`). If it doesn't, stop and ask the user. Measure the impact with a read: `SELECT COUNT(*) FROM t WHERE <same condition>` for UPDATE or DELETE; required columns and existing keys for INSERT.
3. **Plan.** `plan … --sql "<sql>"` prints `WRITE PLAN (nothing has run)` and a token. Show the plan to the user and ask for an explicit yes.
4. **Execute.** Run `execute` with the same arguments plus `--confirm <token>`. The token covers the URL, the properties (for a secret, its source), SQL and binds. Any change means a new plan and a new approval (exit 3).
5. **Verify.** No row count comes back, so verify DML with `query` and DDL with `tables`/`columns`.

## How DataRobot runs the SQL

- **Reads** run inside a subquery with a row limit, e.g. `select * from (<sql>) as "_table" fetch next N rows only` on PostgreSQL.
  - Send one query. The script strips a trailing `;` and trailing comments.
  - Your own LIMIT is fine and saves the database work.
  - SHOW, DESCRIBE and EXPLAIN cannot run: use `tables`/`columns` or catalog queries.
  - SQL Server: column names must be unique, ORDER BY needs TOP, and CTEs fail.
  - BigQuery: quote names with backticks, as in `` `project.dataset.table` ``; `tables` and `columns` need `--schema <dataset>`.
  - Error positions count from the start of the wrapped SQL.
- **Writes** are one JDBC `execute()` call with the driver's autocommit. There is no transaction across statements, and most drivers reject several statements in one call, so send one statement per `execute`. The server cancels the call after 30 s.
- **Values** come back as strings or `NULL`; the `# types:` line comes from `resultSchema`. A `# warning: hit maxRows` line means rows were probably cut.

## Rules

- **Never** pass `--confirm` until the user has approved that exact plan.
- **Never** retry a write after exit 2 until a read shows its effect: the outcome is unknown.
- Writes run as the database user in the properties: suggest a least-privileged user.
- `query` runs only reads. `execute` runs only SQL the user approved verbatim in a plan; an app must never send generated SQL to `/jdbcExecution/` by itself.
- Keep results small; save large results with `--out FILE`.

## Common errors

| Error | Fix |
|---|---|
| 400 `The connection attempt failed.` | DataRobot cannot reach the host: check the host, the port, and that the database firewall allows DataRobot |
| 400 `No suitable JDBC driver…` | Unsupported URL prefix; see `references/jdbc-urls.md` |
| 403 `… Details: …` naming a privilege (`permission denied`, `insufficient privileges`, `command denied`) | The login works but lacks grants (USAGE on the schema, SELECT on the table) |
| 403 `… Details: …` (authentication) | The database rejected the user or the password |
| 400 `SQL [select * from (…)…]; …` | A SQL error in the wrapped query; check the dialect notes |
| 408 `Request timed out…` | `query` and discovery stop at 300 s: narrow the query, or let a cold warehouse start. `execute` stops at 30 s, login included: warm the warehouse with a `query` first. A timed-out write may still have run |
| 422 `… is not allowed key` | Use camelCase fields. JDBC routes have no `credentialId` |

Full list: `references/api-reference.md`.

## Wiring an app (Talk to My Data)

To move an app's SQL onto these routes, follow `references/app-integration.md`: a minimal client, type restoration, timeouts and truncation, and the Talk to My Data migration checklist.

In Talk to My Data, the JDBC-URL source maps to `/jdbcDataPreview/`. Its DataRobot data-connection sources map to `datarobot-connectivity-datastore-sql`.

## Using DataRobot SDK

The script calls REST directly. That avoids SDK client retries, which could run a write twice, and keeps driver property names unchanged. In the `datarobot` SDK:

- `JdbcPreview.execute_update(...)` calls `/jdbcExecution/`.
- `JdbcPreview.preview(...)` in **3.19+** calls `/jdbcPreviewQuery/`, which some accounts and app API keys cannot use (403). For reads, prefer a direct `POST {DATAROBOT_ENDPOINT}/jdbcDataPreview/`.


## References

- `references/api-reference.md`: request and response contract, limits, errors
- `references/jdbc-urls.md`: URL templates, auth properties, dialect limits, catalog SQL
- `references/app-integration.md`: Python clients, types, and the Talk to My Data checklist

## Related skills

- `datarobot-connectivity-datastore-sql`: SQL through a DataRobot data connection with stored credentials
- `datarobot-setup`: authentication and SDK setup
