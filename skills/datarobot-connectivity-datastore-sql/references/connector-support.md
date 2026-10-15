# Connector support and SQL dialects

What each kind of data connection supports, and how to write SQL for it.

**Contents:** Capability by driver · Transactions on writes · Dialect cheat sheet · DDL differences · Discovery SQL

## Capability by driver

`datastore_sql.py datastores` prints this as the `sql` column. It is derived from the connection's `type` and `driverClassType`.

| `driverClassType` | Source | Reads | Writes (`executeUpdate/`) |
|---|---|---|---|
| `snowflake` (type `jdbc`) | Snowflake | fast | yes |
| `databricks-v1` | Databricks | fast | yes |
| `bigquery-v1` | Google BigQuery | fast | yes |
| `datasphere-v1` | SAP Datasphere | fast | yes |
| `trino-v1` | Trino | fast | yes |
| `salesforce-v1` | Salesforce | fast | no (400) |
| any other `jdbc` driver: `postgres`, `mysql`, `mssql`, `oracle`, `sap` (HANA), `redshift`, `bigquery1`/`bigquery2`, `unknown`, … | various | legacy | no: 409 `SQL execution is not supported for this data store.` |
| type `dr-connector-v1`: `native-s3`, `native-adls`, `native-gdrive`, … | files and objects | no SQL: 409 | no |

- **Fast** means DataRobot's native connector service, which typically answers in about 1–2 s.
- **Legacy** is slower (several seconds per call), drops bind parameters, and may format values differently.
- SAP Datasphere connections need the SAP Datasphere connector enabled for the organization; otherwise you get a 403.
- To write to a legacy-path database, use `datarobot-connectivity-jdbc-sql` with its JDBC URL and credentials.

## Transactions on writes

The script sends the SQL **verbatim in one request**. What happens to several statements in one request depends on the connector:

| Connector | Several statements in one request |
|---|---|
| Snowflake | Run in **one transaction**: all or nothing |
| Databricks | No transaction: statements that ran before a failure stay applied |
| Trino | Autocommit; most Trino catalogs reject multi-statement transactions. Send one statement per request |
| BigQuery, SAP Datasphere | Connector-specific; send one statement per request |

No row counts come back. After a write, check the effect with a read, for example `SELECT COUNT(*) …`.

## Dialect cheat sheet

| Source | Row limit | Quote identifiers | Notes |
|---|---|---|---|
| Snowflake | `LIMIT n` | `"Name"` | Unquoted names are folded to upper case; `db.schema.table` |
| Databricks | `LIMIT n` | `` `name` `` | `catalog.schema.table` (Unity Catalog) |
| BigQuery | `LIMIT n` | `` `project.dataset.table` `` | Standard SQL; dates via `DATE(...)` and `TIMESTAMP(...)` |
| SAP Datasphere / HANA | `LIMIT n` | `"Name"` | A Datasphere space is a schema. Constants need `FROM DUMMY`. Quote names that are mixed-case or start with a digit, e.g. `"SPACE"."10k_view"` |
| Trino | `LIMIT n` | `"name"` | `catalog.schema.table` |
| PostgreSQL / Redshift | `LIMIT n` | `"name"` | Unquoted names are folded to lower case; `ORDER BY x DESC` puts NULLs first, so add `NULLS LAST` for top-N |
| MySQL | `LIMIT n` | `` `name` `` | |
| SQL Server | `SELECT TOP n …` | `[name]` | No `LIMIT` |
| Oracle | `FETCH FIRST n ROWS ONLY` | `"NAME"` | Constants need `FROM DUAL` |

On the legacy fallback for `preview`, the script builds `SELECT * FROM <catalog>.<schema>.<table>`. It quotes each name you pass: backticks for MySQL, BigQuery and Databricks, double quotes elsewhere. So pass names exactly as stored, in the stored case, e.g. `--schema TESTSPACE --table BOOL_view`.

In every dialect, quote identifiers that are mixed-case, start with a digit, contain spaces or special characters, or are reserved words.

## DDL differences

| Source | Add a column | Notes |
|---|---|---|
| Snowflake | `ALTER TABLE t ADD COLUMN notes VARCHAR(200)` | DDL commits immediately, even inside a multi-statement request |
| Databricks | `ALTER TABLE t ADD COLUMN notes STRING` | Delta tables; there is no transaction around the request |
| BigQuery | ``ALTER TABLE `p.ds.t` ADD COLUMN notes STRING`` | New columns must be nullable |
| SAP Datasphere / HANA | `ALTER TABLE "SPACE"."T" ADD (NOTES NVARCHAR(200))` | Parentheses around the column list; new columns are nullable by default. Only Datasphere connections can write here; HANA (`sap`) connections are read-only |
| Trino | `ALTER TABLE t ADD COLUMN notes VARCHAR` | Support depends on the catalog's connector |

## Discovery SQL

The `tables` and `columns` commands work for every SQL connection but run on the slower legacy path and need a credential. On fast connections, catalog SQL through `query` is quicker:

| Source | List tables | List columns |
|---|---|---|
| Snowflake | `SELECT table_schema, table_name, table_type FROM information_schema.tables WHERE table_schema <> 'INFORMATION_SCHEMA'` | `SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'S' AND table_name = 'T' ORDER BY ordinal_position` |
| Databricks | `SELECT table_schema, table_name, table_type FROM <catalog>.information_schema.tables` | `SELECT column_name, data_type FROM <catalog>.information_schema.columns WHERE table_schema = 's' AND table_name = 't'` |
| BigQuery | ``SELECT table_name, table_type FROM `<project>.<dataset>.INFORMATION_SCHEMA.TABLES` `` | ``SELECT column_name, data_type FROM `<project>.<dataset>.INFORMATION_SCHEMA.COLUMNS` WHERE table_name = 't'`` |
| SAP Datasphere / HANA | `SELECT SCHEMA_NAME, VIEW_NAME FROM SYS.VIEWS WHERE SCHEMA_NAME = 'SPACE'` (also `SYS.TABLES`) | `SELECT COLUMN_NAME, DATA_TYPE_NAME FROM SYS.VIEW_COLUMNS WHERE SCHEMA_NAME = 'SPACE' AND VIEW_NAME = 'V'` (tables: `SYS.TABLE_COLUMNS`) |
| Trino | `SELECT table_schema, table_name FROM <catalog>.information_schema.tables` | `SELECT column_name, data_type FROM <catalog>.information_schema.columns WHERE table_name = 't'` |
| PostgreSQL, Redshift, MySQL, SQL Server | `SELECT table_schema, table_name FROM information_schema.tables` | `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 't'` |

For column names and types without data, run the query with `WHERE 1=0`; `resultSchema` still comes back.
