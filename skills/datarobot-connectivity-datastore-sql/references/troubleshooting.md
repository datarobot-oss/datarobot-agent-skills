# Troubleshooting

Errors from `datastore_sql.py` and the datastore routes, with causes and fixes. The script prints a matching `hint:` line for the most common ones.

| Symptom | Cause | Fix |
|---|---|---|
| 401, often with an empty body | API token missing, expired, or for another DataRobot instance | Check `DATAROBOT_ENDPOINT`/`DATAROBOT_API_TOKEN`; run the `datarobot-setup` skill |
| `DATAROBOT_API_TOKEN is not set` (or `…ENDPOINT…`) | Only one of the two variables is set | Set both, or unset both so both come from `drconfig.yaml`. The endpoint and token always come from one source |
| HTTP 301/302/307 with a `redirect` hint | `DATAROBOT_ENDPOINT` points at a proxy, a login page, or an `http://` URL that redirects | Use the exact `https://<host>/api/v2` URL. The script never follows redirects, because they would carry the token elsewhere |
| 403 `… (Enable the Future Public API).` | Newer routes not enabled for the account | Reads fall back to `/verifySQL/` automatically. For writes, ask a DataRobot admin, or use `datarobot-connectivity-jdbc-sql` |
| 403 `Access denied due to seat license restrictions` | Seat type excludes `/previewQuery/` | Reads fall back to `/verifySQL/` automatically; `--route legacy` forces it |
| 422 `Credentials were not provided and default credentials were not found.` | No `--credential-id` and no default credential. **Checked before the connection id**, so a wrong id shows the same error | Run `datastores` to confirm the id, then `credentials`; pass `--credential-id` or set a default in DataRobot |
| 404 `Access denied or credential does not exist` | Credential id is wrong or not shared with you | `credentials --datastore-id <id>` |
| 404 (other message) | Connection id is wrong or not shared with you | `datastores --name <text>` |
| 403 `You do not have the required permissions. Details: …` | The **database** rejected the stored login (wrong password, locked user, missing privilege) | Update the credential in DataRobot, or ask the DBA for privileges |
| 400 `invalid_grant…` / OAuth errors | Stored OAuth credential expired or was revoked | Re-authorize the credential in DataRobot, or pick another |
| 400 with a database message | SQL error: the object does not exist, wrong identifier case or quoting, or dialect | Check with `tables`/`columns`; see `connector-support.md`. From `tables` or `columns` itself, the schema or table is missing: list what exists with `schemas` and `tables --schema S` |
| 408 `Request timed out; try again later` on a read | Over the 300 s limit: a stopped warehouse still starting, or a heavy query | Retry once the warehouse is running; add `WHERE`/`LIMIT`/aggregation |
| 409 `SQL execution is not supported for this data store.` | Writes need a native connector (see `connector-support.md`) | Use `datarobot-connectivity-jdbc-sql` with the database's JDBC URL |
| 409 `This operation is only allowed for JDBC data stores` | File or object connector (S3, ADLS, Google Drive, …) | No SQL on this connection |
| 422 `Cannot get results from DSS` / other 422 on the legacy path | Legacy engine timed out or failed | Narrow the query; retry later |
| 429 | Rate limited | Wait, then retry the read |
| `execute` exit 3 with `the --confirm token does not match this plan` | The SQL, binds, credential, or connection changed since the user approved | Show the new plan and get approval again; use its token |
| `execute`: `the following arguments are required: --confirm` (exit 1) | `execute` only runs an approved plan | Run `plan` first, get the user's approval, then `execute … --confirm <token>` |
| `plan` exit 5: `CANNOT WRITE THROUGH DATAROBOT` | The connection's driver has no write support in DataRobot | Nothing to approve. Use `datarobot-connectivity-jdbc-sql` with the database's own JDBC URL |
| Unsure whether this account can use the newer routes | The 403 above depends on account settings | `routes --datastore-id <id>` probes them with empty requests that run no SQL. A route that is available to the account still needs a driver that supports it: `routes` says so for writes |
| `execute` exit 4: `FAILED: the database reported: …` | HTTP 200 with a message other than `OK` | Read the message; check state with a read before changing anything |
| `execute` exit 2: `… may or may not have run` | Timeout (408), server error (5xx), dropped connection, or unreadable response during a write | **Do not re-run.** Check state with `query` first |
| `query`/`preview` refuses SQL (exit 1) | Only one read statement (SELECT, WITH, VALUES, SHOW, DESCRIBE, EXPLAIN) without INSERT, UPDATE, DELETE, MERGE, or INTO is allowed. The check considers every dialect's quoting and comment rules | Run statements one at a time; use `plan` and `execute` (with approval) for writes |
| `tables`/`columns` return no rows | Discovery lists only objects the credential can access, or the schema or table name is wrong | Check the name and its case; ask for grants if the object should exist |
| `The SQL has an unterminated quote or comment` | A quote or comment never closes | Fix the SQL |
| `Bind parameters are ignored for <driver> connections` | Legacy-path driver drops binds | Inline the values as SQL literals |
| `datastores` misses connections visible in the UI | Raw API calls without `type=all` list only legacy JDBC connections | The script always sends `type=all`; do the same in your own calls |
| Table "not found" on the legacy `preview` route | The script quotes the names you pass, so they match case exactly | Pass names exactly as stored, e.g. `--schema TESTSPACE --table BOOL_view` |
| `is not a DataRobot id` | `--datastore-id`/`--credential-id` must be 24 hex characters | Copy the id from `datastores` or `credentials` |
| SSL errors against a self-managed install | Private CA | `DATAROBOT_SSL_VERIFY=/path/to/ca.pem` (or `false` for testing only) |
