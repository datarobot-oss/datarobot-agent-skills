# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for the datarobot-connectivity-jdbc-sql skill script.

The script must:
  - call only the live routes /jdbcDataPreview/ and /jdbcExecution/ with
    camelCase bodies (no credentialId, no maxRows on execute);
  - keep secrets out of all output: URL credentials (including passwords with
    '@' or brace quoting), sensitive driver properties, the API token, and any
    error text that echoes them;
  - load --env-file before DataRobot auth, so its credentials are honoured;
  - run a write only with the --confirm token of the approved plan, never
    retry it, report an unknown outcome when the response is missing or the
    statement may have reached the database, and treat only "OK" as success;
  - refuse statements the preview cannot run (writes, SHOW/DESCRIBE, hidden
    extra statements) and strip trailing comments before wrapping.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills/datarobot-connectivity-jdbc-sql/scripts/jdbc_sql.py"
)
TOKEN = "test-token-must-never-be-printed"
SECRET = "db-secret-must-never-be-printed"
URL = "jdbc:postgresql://db.example.test:5432/sales"
ENV_NAMES = (
    "JDBC_URL",
    "JDBC_URI",
    "JDBC_CONNECTION_PARAMETERS",
    "DATAROBOT_ENDPOINT",
    "DATAROBOT_API_TOKEN",
    "DATAROBOT_CONFIG_FILE",
)


@pytest.fixture
def mod() -> Any:
    """Load a fresh module per test so the secret registry starts empty."""
    spec = importlib.util.spec_from_file_location("_jdbc_sql", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_jdbc_sql"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no-config"))
    monkeypatch.setenv("DATAROBOT_ENDPOINT", "https://dr.example.test/api/v2")
    monkeypatch.setenv("DATAROBOT_API_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PASSWORD", SECRET)
    return monkeypatch


@pytest.fixture
def api(
    mod: Any, env: pytest.MonkeyPatch
) -> Callable[[dict[str, Any]], list[dict[str, Any]]]:
    """Replace DataRobotClient.post. Values may be dicts or exceptions."""

    def install(routes: dict[str, Any]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []

        def fake_post(
            self: Any, route: str, body: dict[str, Any], **kwargs: Any
        ) -> Any:
            calls.append({"route": route, "body": body, **kwargs})
            value = routes[route]
            if isinstance(value, BaseException):
                raise value
            return value(body) if callable(value) else value

        env.setattr(mod.DataRobotClient, "post", fake_post)
        return calls

    return install


PREVIEW = {
    "columns": ["id", "name"],
    "records": [["1", "a"], ["2", None]],
    "resultSchema": [
        {"name": "id", "dataType": "INTEGER", "dataTypeInt": 4},
        {"name": "name", "dataType": "VARCHAR", "dataTypeInt": 12},
    ],
}
CONN = ["--jdbc-url", URL, "--param", "user=app", "--param-env", "password=DB_PASSWORD"]


def all_output(capsys: Any) -> str:
    captured = capsys.readouterr()
    return str(captured.out + captured.err)


# --------------------------------------------------------------------------- #
# Masking and connection input
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("url", "hidden"),
    [
        ("jdbc:postgresql://u:pw123@h:5432/db", "pw123"),
        (
            "jdbc:mysql://myuser@srv:S3cretPw@srv.mysql.database.azure.com:3306/db",
            "S3cretPw",
        ),
        ("jdbc:mysql://u:p@ss@h/db", "p@ss"),
        ("jdbc:mysql://u:pw/123@h/db", "pw/123"),
        ("jdbc:mysql://h:3306/db?user=u&password=pw123&ssl=true", "pw123"),
        ("jdbc:sqlserver://h;password={pw;123};encrypt=true", "pw;123"),
        ("jdbc:databricks://h:443;AuthMech=3;PWD={dapi;abc}", "dapi;abc"),
        ("jdbc:mysql://(host=h,user=u,password=pw123)/db", "pw123"),
        ("jdbc:mysql://address=(host=h)(password=pw123)/db", "pw123"),
        ("jdbc:sqlserver://h;keyVaultProviderClientKey=kv123", "kv123"),
        ("jdbc:snowflake://a.snowflakecomputing.com/?private_key_pwd=pw123", "pw123"),
    ],
)
def test_mask_url_hides_credentials(mod: Any, url: str, hidden: str) -> None:
    masked = mod.mask_url(url)
    assert hidden not in masked and "***" in masked


def test_mask_url_keeps_non_secret_properties(mod: Any) -> None:
    url = "jdbc:sqlserver://h:1433;databaseName=db;encrypt=true"
    assert mod.mask_url(url) == url
    bigquery = "jdbc:bigquery://https://www.googleapis.com/bigquery/v2:443;ProjectId=p"
    assert mod.mask_url(bigquery) == bigquery


def test_connection_from_talk_to_my_data_env_names(
    mod: Any, env: pytest.MonkeyPatch
) -> None:
    env.setenv("JDBC_URI", URL)
    env.setenv(
        "JDBC_CONNECTION_PARAMETERS",
        '{"user": "app", "ssl": true, "port": 5432, "role": null}',
    )
    conn = mod.build_connection(mod.build_parser().parse_args(["check"]))
    assert conn.url == URL
    assert conn.parameters == {"user": "app", "ssl": "true", "port": "5432"}
    assert conn.dialect == "postgresql"


def test_json_properties_only_travel_with_their_url(
    mod: Any, env: pytest.MonkeyPatch, capsys: Any
) -> None:
    env.setenv("JDBC_URL", URL)
    env.setenv("JDBC_CONNECTION_PARAMETERS", '{"user": "wh", "password": "wh-pw"}')
    other = "jdbc:postgresql://other.example.test:5432/db"
    parse = mod.build_parser().parse_args

    explicit = mod.build_connection(parse(["check", "--jdbc-url", other]))
    assert explicit.parameters == {}
    assert "JDBC_CONNECTION_PARAMETERS is ignored" in capsys.readouterr().err

    opted_in = ["check", "--jdbc-url", other]
    opted_in += ["--params-json-env", "JDBC_CONNECTION_PARAMETERS"]
    assert mod.build_connection(parse(opted_in)).parameters["user"] == "wh"
    assert mod.build_connection(parse(["check"])).parameters["user"] == "wh"


def test_env_file_parsing(mod: Any, env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import os

    env.setattr(os, "environ", dict(os.environ))  # load_env_file writes os.environ
    env_file = tmp_path / ".env"
    env_file.write_text(
        "﻿JDBC_URL=" + URL + "  # staging\n"
        'export QUOTED="s3cret # not a comment" # prod\n'
        "HASHED=ab#c\n"
        "DB_PASSWORD=from-file\n"
        "# comment\n",
        encoding="utf-8",
    )
    mod.load_env_file(str(env_file))
    assert os.environ["JDBC_URL"] == URL
    assert os.environ["QUOTED"] == "s3cret # not a comment"
    assert os.environ["HASHED"] == "ab#c"
    assert os.environ["DB_PASSWORD"] == SECRET  # existing values win


@pytest.mark.parametrize(
    "argv",
    [
        ["check"],
        ["check", "--jdbc-url", ""],
        ["check", "--jdbc-url", "postgresql://h/db"],
        ["check", "--jdbc-url", URL, "--param-env", "password=MISSING_VAR"],
        ["check", "--jdbc-url-env", ""],
    ],
)
def test_bad_connection_input_is_a_usage_error(
    mod: Any, api: Any, argv: list[str]
) -> None:
    api({})
    assert mod.main(argv) == 1


def test_param_errors_do_not_echo_values(mod: Any, api: Any, capsys: Any) -> None:
    api({})
    assert mod.main(["check", "--jdbc-url", URL, "--param", "password:hunter2"]) == 1
    assert "hunter2" not in all_output(capsys)


def test_secret_on_command_line_triggers_warnings(
    mod: Any, api: Any, capsys: Any
) -> None:
    api({"jdbcDataPreview/": PREVIEW})
    mod.main(["check", "--jdbc-url", "jdbc:mysql://u:pw123@h/db"])
    output = all_output(capsys)
    assert "contains a secret" in output and "pw123" not in output
    mod.main(["check", "--jdbc-url", URL, "--param", "password=plain-secret"])
    output = all_output(capsys)
    assert (
        "prefer --param-env password=ENV_VAR" in output and "plain-secret" not in output
    )


# --------------------------------------------------------------------------- #
# SQL guard and catalog SQL
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("sql", ["SHOW TABLES", "describe t", "EXPLAIN SELECT 1"])
def test_unwrappable_reads_are_refused(mod: Any, sql: str) -> None:
    with pytest.raises(mod.UsageError, match="subquery"):
        mod.check_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM t",
        "SELECT 1; SELECT 2",
        "WITH d AS (DELETE FROM t RETURNING *) SELECT 1",
        "SELECT * INTO t2 FROM t",
        "SELECT '\\'', 1; DELETE FROM t WHERE TRUE; SELECT '1'",
        "SELECT 1 # '\n; DELETE FROM t",
        "select a$b$c from t; delete from t",
        "SET x = 1",
    ],
)
def test_writes_and_hidden_statements_are_refused(mod: Any, sql: str) -> None:
    with pytest.raises(mod.UsageError):
        mod.check_read_only(sql)


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT * FROM t -- latest", "SELECT * FROM t"),
        ("SELECT 1\n-- end of query\n", "SELECT 1"),
        ("SELECT 1;;", "SELECT 1"),
        ("VALUES (1)", "VALUES (1)"),
        ("SELECT $fn1$ a b $fn1$ AS body", "SELECT $fn1$ a b $fn1$ AS body"),
    ],
)
def test_reads_are_cleaned_for_the_wrapper(mod: Any, sql: str, expected: str) -> None:
    assert mod.check_read_only(sql) == expected


def test_catalog_sql_per_dialect(mod: Any) -> None:
    assert "pg_catalog" in mod.tables_sql("postgresql", None, None)
    assert "performance_schema" in mod.tables_sql("mysql", None, None)

    sqlserver = mod.tables_sql("sqlserver", None, "dbo")
    assert (
        "FROM INFORMATION_SCHEMA.TABLES" in sqlserver
        and "UPPER(TABLE_SCHEMA)" in sqlserver
    )
    assert "ORDER BY" not in sqlserver
    columns = mod.columns_sql("sqlserver", "crm", None, "Orders")
    assert (
        "FROM [crm].INFORMATION_SCHEMA.COLUMNS" in columns
        and "UPPER(TABLE_NAME)" in columns
    )

    hana = mod.columns_sql("sap", None, "SPACE", "orders")
    assert "SYS.TABLE_COLUMNS" in hana and "SYS.VIEW_COLUMNS" in hana
    assert "UPPER(TABLE_NAME) = UPPER('orders')" in hana
    assert "SYS.TABLES" in mod.tables_sql("sap", None, None)
    assert mod.check_sql("sap").endswith("FROM DUMMY")

    assert "`p`.`ds`.INFORMATION_SCHEMA.TABLES" in mod.tables_sql("bigquery", "p", "ds")
    with pytest.raises(mod.UsageError):
        mod.tables_sql("bigquery", None, None)
    assert '"CAT".information_schema.tables' in mod.tables_sql("trino", "CAT", None)
    with pytest.raises(mod.UsageError, match="--catalog"):
        mod.tables_sql("postgresql", "other_db", None)

    assert "O''Brien" in mod.columns_sql("postgresql", None, None, "O'Brien")
    assert "'a\\\\b\\'c'" in mod.columns_sql("databricks", None, None, "a\\b'c")


@pytest.mark.parametrize(
    "dialect",
    ["snowflake", "redshift", "postgresql", "oracle", "mysql", "sqlserver", "trino"],
)
def test_backslash_cannot_end_a_catalog_literal_early(mod: Any, dialect: str) -> None:
    # Snowflake and Redshift read `\'` as an escaped quote, so `x\'' OR ...`
    # would close the string unless the backslash is doubled too.
    columns = mod.columns_sql(dialect, None, None, "x\\' OR 1=1 --")
    assert "UPPER('x\\\\'' OR 1=1 --')" in columns
    tables = mod.tables_sql(dialect, None, "x\\' OR 1=1 --")
    assert "UPPER('x\\\\'' OR 1=1 --')" in tables


def test_backslash_cannot_end_a_sap_literal_early(mod: Any) -> None:
    columns = mod.columns_sql("sap", None, "s\\' OR 1=1 --", "t\\' OR 1=1 --")
    assert columns.count("UPPER('t\\\\'' OR 1=1 --')") == 2
    assert columns.count("UPPER('s\\\\'' OR 1=1 --')") == 2


@pytest.mark.parametrize("dialect", ["bigquery", "databricks", "spark"])
def test_backslash_in_an_identifier_is_rejected(mod: Any, dialect: str) -> None:
    # A backslash can escape the closing backtick in these dialects.
    with pytest.raises(mod.UsageError, match="backslash"):
        mod.tables_sql(dialect, "c\\", "s")


def test_postgres_discovery_uses_pg_catalog(mod: Any) -> None:
    tables = mod.tables_sql("postgresql", None, "rnacen")
    assert "pg_catalog.pg_class" in tables and "has_table_privilege" in tables
    assert "UPPER(n.nspname) = UPPER('rnacen')" in tables
    columns = mod.columns_sql("postgresql", None, "rnacen", "rnc_database")
    assert "pg_catalog.pg_attribute" in columns and "format_type" in columns
    assert "information_schema" in mod.tables_sql("redshift", None, None)


def test_discovery_explains_empty_and_unreadable_results(
    mod: Any, api: Any, capsys: Any
) -> None:
    rows = [["rnacen", "rnc_database", "TABLE", "False"]]
    api({"jdbcDataPreview/": {"columns": ["s", "n", "t", "r"], "records": rows}})
    assert mod.main(["tables", *CONN, "--schema", "rnacen"]) == 0
    assert "readable=False" in capsys.readouterr().out
    api({"jdbcDataPreview/": {"columns": ["s", "n", "t", "r"], "records": []}})
    assert mod.main(["tables", *CONN, "--schema", "nope"]) == 0
    assert "no rows: catalog views list only objects" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("details", "hint"),
    [
        ("ERROR: permission denied for schema rnacen", "lacks a privilege"),
        ("The SELECT permission was denied on the object 't'", "lacks a privilege"),
        ("SELECT command denied to user 'u'@'h' for table 't'", "lacks a privilege"),
        ("Insufficient privileges to operate on schema 'S'", "lacks a privilege"),
        ("[INSUFFICIENT_PERMISSIONS] Insufficient privileges", "lacks a privilege"),
        ("Access Denied: Cannot select from table t", "lacks a privilege"),
        ("Access denied for user 'u'@'h' (using password: YES)", "rejected the login"),
        ("FATAL: password authentication failed for user", "rejected the login"),
    ],
)
def test_privilege_errors_get_a_grants_hint(
    mod: Any, api: Any, capsys: Any, details: str, hint: str
) -> None:
    denied = (
        f"You do not have the required permissions. Details: SQL [select 1]; {details}"
    )
    api({"jdbcDataPreview/": mod.ApiError(403, denied)})
    assert mod.main(["query", *CONN, "--sql", "SELECT 1"]) == 2
    assert hint in capsys.readouterr().err


def test_tables_are_filtered_and_sorted_client_side(
    mod: Any, api: Any, capsys: Any
) -> None:
    rows = [
        ["b", "Orders", "BASE TABLE"],
        ["a", "order_x", "VIEW"],
        ["a", "users", "VIEW"],
    ]
    calls = api({"jdbcDataPreview/": {"columns": ["s", "n", "t"], "records": rows}})
    assert mod.main(["tables", *CONN, "--like", "ORDER"]) == 0
    assert "LOWER(c.relname) LIKE '%order%'" in calls[0]["body"]["sql"]
    out = capsys.readouterr().out
    assert out.index("order_x") < out.index("Orders") and "users" not in out


@pytest.mark.parametrize(
    ("dialect", "schema", "expected"),
    [
        ("postgresql", "s", ["LOWER(c.relname) LIKE '%a_b%'"]),
        ("sqlserver", "dbo", ["AND LOWER(TABLE_NAME) LIKE '%a_b%'"]),
        ("bigquery", "ds", ["WHERE LOWER(table_name) LIKE '%a_b%'"]),
        ("mysql", None, ["AND LOWER(table_name) LIKE '%a_b%'"]),
        (
            "sap",
            None,
            ["LOWER(TABLE_NAME) LIKE '%a_b%'", "LOWER(VIEW_NAME) LIKE '%a_b%'"],
        ),
    ],
)
def test_like_runs_in_the_catalog_query_as_a_superset(
    mod: Any, dialect: str, schema: str | None, expected: list[str]
) -> None:
    sql = mod.tables_sql(dialect, None, schema, "A[B")
    assert all(part in sql for part in expected), sql
    assert "LIKE '%a_b%'" in mod.tables_sql("postgresql", None, None, "a\\b")
    assert "LIKE" not in mod.tables_sql("postgresql", None, None)


def test_like_warns_when_the_catalog_query_was_cut(
    mod: Any, api: Any, capsys: Any
) -> None:
    rows = [["s", "orders", "TABLE"], ["s", "users", "TABLE"]]
    api({"jdbcDataPreview/": {"columns": ["s", "n", "t"], "records": rows}})
    assert mod.main(["tables", *CONN, "--like", "ord", "--max-rows", "2"]) == 0
    out = capsys.readouterr().out
    assert "1 of 2 fetched names contain 'ord'" in out
    assert "hit --max-rows 2, so matches may be missing" in out


def test_columns_flag_a_table_the_login_cannot_read(
    mod: Any, api: Any, capsys: Any
) -> None:
    rows = [["rnacen", "1", "id", "bigint", "NO", "False"]]
    api({"jdbcDataPreview/": {"columns": list("spcdnr"), "records": rows}})
    assert mod.main(["columns", *CONN, "--table", "rnc_database"]) == 0
    assert "readable=False" in capsys.readouterr().out
    assert "has_table_privilege" in mod.columns_sql("postgresql", None, "s", "t")


def test_check_names_the_login_and_masks_secrets(
    mod: Any, api: Any, capsys: Any
) -> None:
    api({"jdbcDataPreview/": {"columns": ["ok"], "records": [["1"]]}})
    assert mod.main(["check", *CONN]) == 0
    out = capsys.readouterr().out
    assert "'user': 'app'" in out and "'password': '*** (env DB_PASSWORD)'" in out
    assert SECRET not in out


def test_discovery_prints_more_rows_than_reads_by_default(
    mod: Any, api: Any, capsys: Any
) -> None:
    rows = [["s", f"t{i:02}", "TABLE"] for i in range(30)]
    api({"jdbcDataPreview/": {"columns": ["s", "n", "t"], "records": rows}})
    assert mod.main(["tables", *CONN]) == 0
    out = capsys.readouterr().out
    assert "t29" in out and "more row" not in out
    assert mod.main(["query", *CONN, "--sql", "SELECT 1"]) == 0
    assert "# ... 10 more rows" in capsys.readouterr().out


def test_columns_are_sorted_by_schema_and_position(
    mod: Any, api: Any, capsys: Any
) -> None:
    rows = [["public", "10", "z"], ["archive", "1", "a"], ["public", "2", "b"]]
    api({"jdbcDataPreview/": {"columns": ["s", "p", "c"], "records": rows}})
    assert mod.main(["columns", *CONN, "--table", "orders", "--format", "json"]) == 0
    records = json.loads(capsys.readouterr().out)["records"]
    assert records == [
        ["archive", "1", "a"],
        ["public", "2", "b"],
        ["public", "10", "z"],
    ]


def test_bind_values_must_be_non_empty_scalars(mod: Any) -> None:
    assert mod.parse_binds('[1, "a", null, true]') == [1, "a", None, True]
    assert mod.parse_binds("[]") is None
    for bad in ('[""]', '[{"a": 1}]', '{"a": 1}', "not json"):
        with pytest.raises(mod.UsageError):
            mod.parse_binds(bad)


# --------------------------------------------------------------------------- #
# Routes and bodies
# --------------------------------------------------------------------------- #


def test_query_posts_camel_case_body(mod: Any, api: Any, capsys: Any) -> None:
    calls = api({"jdbcDataPreview/": PREVIEW})
    code = mod.main(
        ["query", *CONN, "--sql", "SELECT id, name FROM t; -- x", "--bind", "[1]"]
    )
    assert code == 0
    assert calls == [
        {
            "route": "jdbcDataPreview/",
            "body": {
                "jdbcUrl": URL,
                "sql": "SELECT id, name FROM t",
                "maxRows": 100,
                "parameters": {"user": "app", "password": SECRET},
                "bindParams": [1],
            },
            "timeout": mod.PREVIEW_TIMEOUT,
            "retries": 1,
        }
    ]
    out = capsys.readouterr().out
    assert "id INTEGER" in out and "NULL" in out and SECRET not in out


def test_check_uses_a_trivial_query(mod: Any, api: Any, capsys: Any) -> None:
    calls = api({"jdbcDataPreview/": {"columns": ["ok"], "records": [["1"]]}})
    assert mod.main(["check", *CONN]) == 0
    assert calls[0]["body"]["sql"] == "SELECT 1 AS ok"
    assert calls[0]["body"]["maxRows"] == 1
    output = all_output(capsys)
    assert "OK: DataRobot reached" in output and SECRET not in output


def test_missing_preview_route_exits_5(mod: Any, api: Any) -> None:
    api({"jdbcDataPreview/": mod.ApiError(404, "Not Found")})
    assert mod.main(["query", *CONN, "--sql", "SELECT 1"]) == 5


def test_routes_probe_sends_no_sql_and_needs_no_jdbc_url(
    mod: Any, api: Any, capsys: Any
) -> None:
    calls = api(
        {
            "jdbcDataPreview/": mod.ApiError(
                422, "Invalid field data (jdbcUrl: is required; sql: is required)"
            ),
            "jdbcExecution/": mod.ApiError(
                422, "Invalid field data (bindParams: bindParams is not allowed key)"
            ),
            "jdbcPreviewQuery/": mod.ApiError(
                403,
                "You do not have access to this functionality "
                "(Enable the Future Public API).",
            ),
        }
    )
    assert mod.main(["routes"]) == 0
    assert [c["body"] for c in calls] == [{"bindParams": []}] * 3
    out = capsys.readouterr().out
    assert "jdbcDataPreview" in out and "| yes" in out
    assert "no (needs API 2.46)" in out and "not enabled for this account" in out
    assert "no SQL ran" in out


def test_routes_reports_missing_routes_and_refused_tokens(
    mod: Any, api: Any, capsys: Any
) -> None:
    api(
        {
            "jdbcDataPreview/": mod.ApiError(404, "Not Found"),
            "jdbcExecution/": mod.ApiError(403, "Forbidden for app-scoped keys"),
            "jdbcPreviewQuery/": mod.ApiError(500, "Internal error"),
        }
    )
    assert mod.main(["routes", "--format", "json"]) == 0
    records = json.loads(capsys.readouterr().out)["records"]
    assert [r[2] for r in records] == [
        "missing on this DataRobot version",
        "refused for this API token",
        "HTTP 500: Internal error",
    ]
    api({"jdbcDataPreview/": mod.ApiError(401, "", from_body=False)})
    assert mod.main(["routes"]) == 2
    assert "API token was rejected" in capsys.readouterr().err


def plan_token_from(output: str) -> str:
    match = re.search(r"--confirm (\w+)", output)
    assert match, output
    return match.group(1)


def test_plan_then_execute_with_token(mod: Any, api: Any, capsys: Any) -> None:
    calls = api({"jdbcExecution/": {"message": "OK"}})
    args = [*CONN, "--sql", "UPDATE t SET a = ?", "--bind", '["x"]']
    assert mod.main(["plan", *args]) == 0
    out = capsys.readouterr().out
    assert "WRITE PLAN (nothing has run)" in out and "UPDATE without WHERE" in out
    assert SECRET not in out and 'binds      : ["x"]' in out
    assert "'password': '*** (env DB_PASSWORD)'" in out
    assert "confirm the target exists and is a table, not a view" in out
    token = plan_token_from(out)
    assert calls == []

    assert mod.main(["execute", *args, "--confirm", "0000000000"]) == 3
    assert "does not match this plan" in capsys.readouterr().out
    assert mod.main(["execute", *args[:-1], '["y"]', "--confirm", token]) == 3

    assert mod.main(["execute", *args, "--confirm", token]) == 0
    assert len(calls) == 1
    assert calls[0]["route"] == "jdbcExecution/" and calls[0]["retries"] == 0
    assert "maxRows" not in calls[0]["body"]


def test_token_tracks_where_a_secret_comes_from_not_its_value(
    mod: Any, api: Any, env: pytest.MonkeyPatch, capsys: Any
) -> None:
    api({})
    sql = ["--sql", "DELETE FROM t WHERE id = 1"]
    assert mod.main(["plan", *CONN, *sql]) == 0
    token = plan_token_from(capsys.readouterr().out)

    env.setenv("DB_PASSWORD", "rotated-password")
    assert mod.main(["plan", *CONN, *sql]) == 0
    assert plan_token_from(capsys.readouterr().out) == token

    env.setenv("PROD_PASSWORD", SECRET)
    other = [*CONN[:-1], "password=PROD_PASSWORD"]
    assert mod.main(["plan", *other, *sql]) == 0
    out = capsys.readouterr().out
    assert plan_token_from(out) != token and "(env PROD_PASSWORD)" in out


def confirmed(mod: Any, api: Any, capsys: Any, response: Any) -> int:
    api({"jdbcExecution/": response})
    args = [*CONN, "--sql", "DELETE FROM t WHERE id = 1"]
    assert mod.main(["plan", *args]) == 0
    token = plan_token_from(capsys.readouterr().out)
    return int(mod.main(["execute", *args, "--confirm", token]))


def test_execute_failure_message_exits_4(mod: Any, api: Any, capsys: Any) -> None:
    assert confirmed(mod, api, capsys, {"message": "deadlock"}) == 4


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (408, "Request timed out; try again later"),
        (429, "too many requests"),
        (502, "<html>bad gateway</html>"),
        (400, "SQL [DELETE FROM t WHERE id = 1]; constraint violated"),
    ],
)
def test_execute_reports_unknown_outcome_when_it_may_have_run(
    mod: Any, api: Any, capsys: Any, status: int, message: str
) -> None:
    assert confirmed(mod, api, capsys, mod.ApiError(status, message)) == 2
    assert "may or may not have run" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (("400", "The connection attempt failed."), 2),
        (("403", "You do not have the required permissions. Details: login failed"), 2),
        (("404", "Not Found"), 5),
    ],
)
def test_execute_definite_failures(
    mod: Any, api: Any, capsys: Any, error: tuple[str, str], expected: int
) -> None:
    raised = mod.ApiError(int(error[0]), error[1])
    assert confirmed(mod, api, capsys, raised) == expected
    assert "may or may not have run" not in capsys.readouterr().err


def test_errors_never_print_secrets_or_token(mod: Any, api: Any, capsys: Any) -> None:
    echo = f"You do not have the required permissions. Details: bad password {SECRET}"
    api({"jdbcDataPreview/": mod.ApiError(403, echo)})
    url_with_secret = f"jdbc:mysql://h:3306/db?user=u&password={SECRET}"
    assert mod.main(["query", "--jdbc-url", url_with_secret, "--sql", "SELECT 1"]) == 2
    output = all_output(capsys)
    assert SECRET not in output and TOKEN not in output
    assert "rejected the login" in output


@pytest.mark.parametrize(
    ("url", "sql", "sent"),
    [
        ("jdbc:mysql://h/db", "SELECT 1 AS ok # note", "SELECT 1 AS ok"),
        ("jdbc:mysql://h/db", "SELECT 'it\\'s' AS s -- note;", "SELECT 'it\\'s' AS s"),
        ("jdbc:mysql://h/db", "SELECT 5 --1", "SELECT 5 --1"),
        ("jdbc:bigquery://h:443", "SELECT 1 AS ok --a\n# b", "SELECT 1 AS ok"),
        ("jdbc:postgresql://h/db", "SELECT 5 # 3", "SELECT 5 # 3"),
        (
            "jdbc:postgresql://h/db",
            "SELECT 1 AS ok /* a /* b */ c */;",
            "SELECT 1 AS ok",
        ),
    ],
)
def test_trailing_comments_are_stripped_the_way_the_database_lexes(
    mod: Any, api: Any, url: str, sql: str, sent: str
) -> None:
    calls = api({"jdbcDataPreview/": PREVIEW})
    assert mod.main(["query", "--jdbc-url", url, "--sql", sql]) == 0
    assert calls[0]["body"]["sql"] == sent


def test_saved_results_do_not_advise_saving_again(
    mod: Any, api: Any, tmp_path: Path, capsys: Any
) -> None:
    rows = [["s", f"t{i}", "TABLE"] for i in range(5)]
    api({"jdbcDataPreview/": {"columns": ["s", "n", "t"], "records": rows}})
    out = tmp_path / "tables.csv"
    argv = ["tables", *CONN, "--show", "0", "--format", "csv", "--out", str(out)]
    assert mod.main(argv) == 0
    printed = capsys.readouterr().out
    assert "# wrote all 5 rows" in printed
    assert "more row" not in printed and "| n |" not in printed
    assert out.read_text(encoding="utf-8").count("\n") == 6


def test_unwritable_out_file_is_not_a_success(
    mod: Any, api: Any, tmp_path: Path, capsys: Any
) -> None:
    api({"jdbcDataPreview/": PREVIEW})
    out = tmp_path / "rows.csv"
    out.mkdir()  # the directory exists, but the file cannot be written
    assert mod.main(["query", *CONN, "--sql", "SELECT 1", "--out", str(out)]) == 1
    captured = capsys.readouterr()
    assert "could not write --out" in captured.err
    assert "id" in captured.out and "wrote all" not in captured.out


def test_json_output_masks_the_url(mod: Any, api: Any, capsys: Any) -> None:
    api({"jdbcDataPreview/": PREVIEW})
    url = "jdbc:mysql://user:pass1234@h/db"
    assert (
        mod.main(["query", "--jdbc-url", url, "--sql", "SELECT 1", "--format", "json"])
        == 0
    )
    output = all_output(capsys)
    assert "pass1234" not in output and "user:***@h" in output


@pytest.mark.parametrize(
    "argv",
    [
        ["query", "--jdbc-url", URL],
        ["execute", "--jdbc-url", URL, "--sql", "DELETE FROM t WHERE id = 1"],
        ["query", "--jdbc-url", URL, "--sql", "SELECT 1", "--max-rows", "abc"],
        ["query", "--jdbc-url", URL, "--sql", "SELECT 1", "--unknown"],
    ],
)
def test_usage_errors_exit_1(mod: Any, api: Any, argv: list[str]) -> None:
    api({})
    with pytest.raises(SystemExit) as raised:
        mod.main(argv)
    assert raised.value.code == 1


# --------------------------------------------------------------------------- #
# Real HTTP layer against a local server
# --------------------------------------------------------------------------- #

Reply = tuple[int, bytes, dict[str, str]]


@pytest.fixture
def server(
    env: pytest.MonkeyPatch,
) -> Iterator[Callable[[list[Reply]], list[dict[str, Any]]]]:
    replies: list[Reply] = []
    seen: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return None

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode() if length else ""
            seen.append(
                {
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": body,
                }
            )
            status, payload, headers = replies.pop(0) if replies else (500, b"", {})
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    env.setenv("DATAROBOT_ENDPOINT", f"http://127.0.0.1:{httpd.server_port}/api/v2")

    def script(sequence: list[Reply]) -> list[dict[str, Any]]:
        replies[:] = sequence
        seen.clear()
        return seen

    yield script
    httpd.shutdown()


def j(payload: Any) -> bytes:
    return json.dumps(payload).encode()


def test_http_reads_retry_once(mod: Any, server: Any) -> None:
    seen = server(
        [(503, j({"message": "busy"}), {"Retry-After": "1"}), (200, j(PREVIEW), {})]
    )
    assert mod.main(["query", *CONN, "--sql", "SELECT 1"]) == 0
    assert len(seen) == 2 and seen[0]["path"] == "/api/v2/jdbcDataPreview/"
    assert seen[0]["auth"] == f"Bearer {TOKEN}"


def http_write(
    mod: Any, server: Any, capsys: Any, reply: Reply
) -> tuple[int, list[dict[str, Any]]]:
    args = [*CONN, "--sql", "DELETE FROM t WHERE id = 1"]
    server([])
    assert mod.main(["plan", *args]) == 0
    token = plan_token_from(capsys.readouterr().out)
    seen = server([reply])
    return int(mod.main(["execute", *args, "--confirm", token])), seen


def test_http_writes_are_never_retried(mod: Any, server: Any, capsys: Any) -> None:
    code, seen = http_write(mod, server, capsys, (503, j({"message": "busy"}), {}))
    assert code == 2 and len(seen) == 1
    assert "may or may not have run" in capsys.readouterr().err


def test_http_unreadable_write_response(mod: Any, server: Any, capsys: Any) -> None:
    code, _ = http_write(mod, server, capsys, (200, b"<html>login</html>", {}))
    assert code == 2
    assert "may or may not have run" in capsys.readouterr().err


def test_http_redirects_are_not_followed(mod: Any, server: Any, capsys: Any) -> None:
    seen = server([(307, b"", {"Location": "http://127.0.0.1:9/steal"})])
    assert mod.main(["query", *CONN, "--sql", "SELECT 1"]) == 2
    assert len(seen) == 1
    output = all_output(capsys)
    assert "redirect" in output and TOKEN not in output and SECRET not in output


def test_env_file_supplies_datarobot_auth(
    mod: Any, server: Any, env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import os

    endpoint = os.environ["DATAROBOT_ENDPOINT"]
    env.delenv("DATAROBOT_ENDPOINT")
    env.delenv("DATAROBOT_API_TOKEN")
    env.setattr(os, "environ", dict(os.environ))  # load_env_file writes os.environ
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DATAROBOT_ENDPOINT={endpoint}\nDATAROBOT_API_TOKEN=file-token\nJDBC_URL={URL}\n",
        encoding="utf-8",
    )
    seen = server([(200, j({"columns": ["ok"], "records": [["1"]]}), {})])
    assert mod.main(["check", "--env-file", str(env_file)]) == 0
    assert seen[0]["auth"] == "Bearer file-token"
