# JDBC URLs, drivers, and dialect notes

Build `jdbcUrl` and `parameters` for each database DataRobot can reach, write SQL that survives the preview wrapper, and discover schemas with SQL.

## Contents

- [Drivers and URL templates](#drivers-and-url-templates)
- [Authentication properties](#authentication-properties)
- [Timeouts](#timeouts)
- [Dialect limits](#dialect-limits)
- [Discovery SQL](#discovery-sql)
- [Network reachability](#network-reachability)

## Drivers and URL templates

The URL prefix selects the driver. Which drivers are available depends on the DataRobot version and installation. 400 `No suitable JDBC driver for the configured connection URL` means no available driver accepts the URL: check the prefix spelling (`jdbc:postgresql:`, not `jdbc:postgres:`), then assume that installation lacks the driver.

| Database | Prefix | URL template | Auth `parameters` |
|---|---|---|---|
| PostgreSQL | `jdbc:postgresql:` | `jdbc:postgresql://<host>:5432/<db>` (append `?sslmode=require` as needed) | `user`, `password` |
| MySQL | `jdbc:mysql:` | `jdbc:mysql://<host>:3306/<db>` | `user`, `password` |
| SQL Server | `jdbc:sqlserver:` | `jdbc:sqlserver://<host>:1433;databaseName=<db>;encrypt=true` | `user`, `password` |
| Snowflake | `jdbc:snowflake:` | `jdbc:snowflake://<account>.snowflakecomputing.com/?warehouse=<WH>&db=<DB>&schema=<SCHEMA>` | `user` and `password`, or a key pair (below) |
| Databricks | `jdbc:databricks:` | `jdbc:databricks://<workspace-host>:443;HttpPath=/sql/1.0/warehouses/<id>;SSL=1;AuthMech=3` | `user` = `token`, `password` = `<personal access token>` |
| Trino | `jdbc:trino:` | `jdbc:trino://<host>:443/<catalog>?SSL=true` | `user`, `password` |
| SAP HANA, SAP Datasphere | `jdbc:sap:` | `jdbc:sap://<instance>.hanacloud.ondemand.com:443` | `user`, `password` |
| Amazon Redshift | `jdbc:redshift:` | `jdbc:redshift://<host>:5439/<db>` | `user`, `password` |
| Google BigQuery | `jdbc:bigquery:` | `jdbc:bigquery://https://www.googleapis.com/bigquery/v2:443` | `ProjectId`, `OAuthType` = `0`, `OAuthServiceAcctEmail`, `OAuthPvtKey` = `<service-account JSON>` |

Per-driver notes:

- PostgreSQL: `sslmode` works in the URL or in `parameters`.
- SQL Server: keep `encrypt=true`. Add `trustServerCertificate=true` only to test against a server with a self-signed certificate: it disables certificate validation, so credentials travel over unverified TLS.
- Snowflake: unquoted identifiers are stored upper case.
- Databricks: copy `HttpPath` from the SQL warehouse's connection details. The user is the literal string `token`.
- Trino: the path segment sets the default catalog; `/<catalog>/<schema>` also sets the default schema.
- SAP HANA Cloud and SAP Datasphere both use port 443.
- BigQuery: bundled, but not listed as supported on every installation. `OAuthPvtKey` takes the service-account key JSON as a string.

Snowflake key-pair `parameters` (drop `private_key_pwd` for an unencrypted key):

```json
{"user": "<user>", "authenticator": "SNOWFLAKE_JWT",
 "private_key_base64": "<base64 of the whole PEM file>", "private_key_pwd": "<passphrase>"}
```

Produce the value with `base64 < rsa_key.p8 | tr -d '\n'`.

## Authentication properties

- Put secrets in `parameters`, not in the URL. That keeps them out of URLs and logs.
- Send every value as a string (`"loginTimeout": "10"`, `"ssl": "true"`). The server converts other types to text: `true` becomes `"True"`, `null` becomes `"None"`.
- Multi-line secrets (PEM keys, service-account JSON) are ordinary JSON strings. Build the body with `json.dumps` or `jq`, never by string concatenation.
- Keep the whole `parameters` object in one secret, for example env `JDBC_CONNECTION_PARAMETERS='{"user": "<user>", "password": "<password>"}'`. The bundled CLI reads that variable.
- Use the property names from the driver's documentation.

## Timeouts

DataRobot's deadlines (preview 300 s, execute 30 s) include connecting and logging in. Set login and connect timeouts well below them (for example 10 s) so a slow login fails with the driver's own error instead of a 408. Read and query timeouts cap the query itself: keep them under the deadline but above your slowest expected query.

| Driver | Login or connect | Read or query |
|---|---|---|
| PostgreSQL | `connectTimeout`, `loginTimeout` (seconds) | `socketTimeout` (seconds) |
| MySQL | `connectTimeout` (milliseconds) | `socketTimeout` (milliseconds) |
| SQL Server | `loginTimeout` (seconds; driver default 30) | `socketTimeout` (milliseconds) |
| Snowflake | `loginTimeout` (seconds; driver default 60) | `networkTimeout` (milliseconds), `queryTimeout` (seconds) |
| Others | Varies by driver; see its documentation | |

Cold warehouses (Snowflake, Databricks) can spend the whole 30 s execute deadline logging in. Run a preview against the same URL first, which has 300 s for the warehouse to resume, then call `/jdbcExecution/`.

## Dialect limits

Preview wraps your SQL in a subquery with the dialect's row limit (PostgreSQL: `select * from (<your sql>) as "_table" fetch next <maxRows> rows only`), so the SQL must be valid as a derived table:

| Construct | Preview | Instead |
|---|---|---|
| One `SELECT` with joins, subqueries, `GROUP BY`, `?` binds | Works | — |
| Trailing `;`, several statements | Fails | One statement, no `;` |
| Trailing line comment (`-- note`, MySQL `# note`) | Fails: it comments out the wrapper | Drop it, or end the SQL with a newline |
| `SHOW`, `DESCRIBE`, `EXPLAIN`, `CALL` | Fails | Catalog queries (Discovery SQL) |
| `INSERT`, `UPDATE`, `DELETE`, `MERGE`, DDL | Fails | `/jdbcExecution/` |
| Unnamed or duplicate output columns (`SELECT COUNT(*)`, `SELECT a.id, b.id`) | Fails on SQL Server | Alias them in every dialect: `COUNT(*) AS n`, `b.id AS b_id` |
| `ORDER BY` without `TOP` (SQL Server) | Fails | `SELECT TOP 100 … ORDER BY …` |
| CTE `WITH …` (SQL Server) | Fails | Inline the CTE as a derived table |
| Inner `ORDER BY` with `LIMIT` or `TOP` | Works | Re-sort client-side if the final order matters |
| Top-N with `ORDER BY x DESC` on a nullable column | Works, but PostgreSQL, Redshift, and Snowflake sort NULLs first | Add `NULLS LAST`. MySQL and SQL Server already sort NULLs last on `DESC` and reject `NULLS LAST` |

`maxRows` caps the rows returned, not the work done. Add selective `WHERE` clauses and your own `LIMIT` (`TOP` on SQL Server).

## Discovery SQL

JDBC URLs have no metadata routes: discover through preview. Send one query per call. Sort client-side, because an inner `ORDER BY` isn't guaranteed through the wrapper and SQL Server rejects it. The bundled `tables` and `columns` commands already quote, case-match and sort for you.

Connectivity check: `SELECT 1 AS ok`. On SAP HANA and SAP Datasphere: `SELECT 1 AS ok FROM DUMMY`. Keep the alias; SQL Server rejects an unnamed column.

Tables, then columns, for every dialect except SAP:

```sql
SELECT table_schema, table_name, table_type
FROM <tables view>
WHERE table_schema NOT IN (<system schemas>)

SELECT column_name, data_type, is_nullable, ordinal_position
FROM <columns view>
WHERE table_schema = '<schema>' AND table_name = '<table>'
```

| Dialect | `<tables view>`, `<columns view>` | `<system schemas>` |
|---|---|---|
| PostgreSQL | `information_schema.tables`, `information_schema.columns` | `'pg_catalog', 'information_schema'` |
| Redshift | As PostgreSQL; `svv_tables` also lists external tables | `'pg_catalog', 'information_schema'` |
| MySQL | `information_schema.tables`, `information_schema.columns` | `'mysql', 'information_schema', 'performance_schema', 'sys'` |
| SQL Server | `INFORMATION_SCHEMA.TABLES`, `INFORMATION_SCHEMA.COLUMNS`; write column names upper case (`TABLE_SCHEMA`) | `'sys', 'INFORMATION_SCHEMA'` |
| Snowflake | `information_schema.tables`, `information_schema.columns` (database from the URL's `db`), or `<DB>.information_schema.…` | `'INFORMATION_SCHEMA'` |
| Databricks | `<catalog>.information_schema.tables`, `<catalog>.information_schema.columns`; `system.information_schema.…` covers every catalog you can see | `'information_schema'` |
| Trino | `<catalog>.information_schema.tables`, `<catalog>.information_schema.columns` | `'information_schema'` |
| BigQuery | `` `<project>.<dataset>.INFORMATION_SCHEMA.TABLES` ``, `` `<project>.<dataset>.INFORMATION_SCHEMA.COLUMNS` `` | None: drop the filter (one dataset) |

Match identifier case in `'<schema>'` and `'<table>'`: Snowflake stores unquoted names upper case, Databricks Unity Catalog lower case.

`information_schema` lists only objects the login has some privilege on, so an empty result can mean missing grants rather than a wrong name. On PostgreSQL the bundled `tables` command reads `pg_catalog` instead and adds a `readable` column. To check grants yourself on PostgreSQL:

```sql
SELECT n.nspname AS table_schema, c.relname AS table_name,
       has_schema_privilege(n.oid, 'USAGE') AND has_table_privilege(c.oid, 'SELECT') AS readable
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'v', 'm', 'p', 'f') AND n.nspname = '<schema>'
```

`readable = false` means the login needs `GRANT USAGE ON SCHEMA <schema>` and `GRANT SELECT ON <table>`; a query against such a table returns 403 `permission denied`.

SAP HANA and SAP Datasphere use `SYS` views:

```sql
SELECT SCHEMA_NAME, TABLE_NAME, 'TABLE' AS OBJECT_TYPE FROM SYS.TABLES WHERE SCHEMA_NAME = CURRENT_SCHEMA
UNION ALL
SELECT SCHEMA_NAME, VIEW_NAME, 'VIEW' FROM SYS.VIEWS WHERE SCHEMA_NAME = CURRENT_SCHEMA

SELECT COLUMN_NAME, DATA_TYPE_NAME, IS_NULLABLE, POSITION
FROM SYS.TABLE_COLUMNS
WHERE SCHEMA_NAME = '<SCHEMA>' AND TABLE_NAME = '<TABLE>'
```

Replace `CURRENT_SCHEMA` with `'<SCHEMA>'` to list another schema. For a view's columns, query `SYS.VIEW_COLUMNS` by `VIEW_NAME`.

For values that come from user input, use `?` and `bindParams` (API 2.46+) instead of formatting them into the SQL.

## Network reachability

DataRobot opens the database connection itself, never from your machine:

- SaaS connects from DataRobot's cloud. Self-managed installations connect from the cluster that runs DataRobot.
- A database reachable only from your laptop or office network, `localhost` included, will not work. Use a hostname that DataRobot can reach.
- Firewalls, security groups, and database network rules (such as Snowflake network policies) must admit DataRobot's egress IPs. Ask your DataRobot administrator or DataRobot support for them.
- A blocked path returns 400 with a driver connection error, such as PostgreSQL's `The connection attempt failed.`. If the same URL works from your machine, the problem is reachability from DataRobot, not credentials.
