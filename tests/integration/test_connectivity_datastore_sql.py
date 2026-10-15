# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for the datarobot-connectivity-datastore-sql skill script.

The script must:
  - fall back from /previewQuery/ and /preview/ to legacy /verifySQL/ only when
    the route is unavailable (feature-gated 403 or a JSON 404 "Not Found"),
    never on database errors;
  - keep `query` and `preview` read-only under every SQL dialect's lexing, so
    writes cannot skip the approval step;
  - run a write only with the --confirm token of the approved plan, never retry
    it, report an unknown outcome when the response is missing or unreadable,
    and treat only the message "OK" as success;
  - never print the API token, never follow redirects, and read the endpoint
    and token as a pair from one source.
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
    / "skills/datarobot-connectivity-datastore-sql/scripts/datastore_sql.py"
)
DS = "64ba399095a8142488e0092a"
CRED = "65772b63c82502fec4d85894"
OTHER_CRED = "6798f1f18d1fa6c1ba88a961"
TOKEN = "test-token-must-never-be-printed"
GATED = "You do not have access to this functionality (Enable the Future Public API)."


@pytest.fixture(scope="module")
def mod() -> Any:
    spec = importlib.util.spec_from_file_location("_datastore_sql", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_datastore_sql"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("DATAROBOT_ENDPOINT", "https://dr.example.test/api/v2")
    monkeypatch.setenv("DATAROBOT_API_TOKEN", TOKEN)
    return monkeypatch


Routes = dict[tuple[str, str], Any]


@pytest.fixture
def api(mod: Any, env: pytest.MonkeyPatch) -> Callable[[Routes], list[dict[str, Any]]]:
    """Replace DataRobotClient.call. Values may be dicts, exceptions, or callables."""

    def install(routes: Routes) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []

        def fake_call(self: Any, method: str, path: str, **kwargs: Any) -> Any:
            calls.append({"method": method, "path": path, **kwargs})
            for (route_method, suffix), value in routes.items():
                if route_method == method and path.endswith(suffix):
                    if isinstance(value, BaseException):
                        raise value
                    return value(kwargs) if callable(value) else value
            raise AssertionError(f"unexpected call {method} {path}")

        env.setattr(mod.DataRobotClient, "call", fake_call)
        return calls

    return install


ASSOCIATIONS = {
    "data": [
        {"credentialId": CRED, "name": "svc", "isDefault": True},
        {"credentialId": OTHER_CRED, "name": "other", "isDefault": False},
    ]
}
STORE = {
    "id": DS,
    "canonicalName": "Warehouse",
    "type": "dr-database-v1",
    "driverClassType": "databricks-v1",
    "role": "OWNER",
}
PREVIEW = {
    "columns": ["id", "name"],
    "records": [["1", "a"], ["2", None]],
    "resultSchema": [
        {"name": "id", "dataType": "INTEGER"},
        {"name": "name", "dataType": "VARCHAR"},
    ],
}


def routes_of(calls: list[dict[str, Any]]) -> list[str]:
    return [c["path"].rstrip("/").split("/")[-1] for c in calls]


# --------------------------------------------------------------------------- #
# Read-only guard
# --------------------------------------------------------------------------- #


def test_mask_sql_keeps_positions_and_hides_literals(mod: Any) -> None:
    sql = "SELECT 'drop; table' AS x -- delete\n/* update */ FROM \"t;\" $$x;y$$"
    masked = mod.mask_sql(sql)
    assert len(masked) == len(sql)
    for word in ("drop", "delete", "update", ";"):
        assert word not in masked


def test_mask_sql_raises_on_unterminated_text(mod: Any) -> None:
    with pytest.raises(mod.UnterminatedSQL):
        mod.mask_sql("SELECT 'abc")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "  with x as (select 1 as a) select * from x",
        "SELECT 'DELETE FROM t' AS note",
        "(SELECT 1) UNION (SELECT 2)",
        "SELECT update_count, inserted_at FROM stats",
        "SELECT 'C:\\' AS path",
        "SHOW TABLES",
        "EXPLAIN SELECT * FROM t",
        "VALUES (1), (2)",
    ],
)
def test_guard_allows_reads(mod: Any, sql: str) -> None:
    assert mod.check_read_only(sql) == sql.strip()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM t",
        "WITH gone AS (DELETE FROM t RETURNING *) SELECT * FROM gone",
        "SELECT 1; DROP TABLE t",
        "EXPLAIN ANALYZE DELETE FROM t",
        "EXPLAIN (ANALYZE) SELECT 1",
        "SELECT * INTO new_t FROM t",
        "SELECT a FROM t INTO OUTFILE '/tmp/x'",
        "RM @stage",
        "SET GLOBAL read_only = 0",
        "DO $$ BEGIN DELETE FROM t; END $$",
        "LOAD DATA INFILE 'x' INTO TABLE t",
        "EXPORT DATA OPTIONS(uri='gs://b/*') AS SELECT 1",
        "BULK INSERT t FROM 'f'",
        "'DELETE FROM t'",
        "SELECT * FROM t FOR UPDATE",
        # Statements hidden from one dialect's lexer but visible to another's.
        "SELECT '\\'', 1; DELETE FROM d.t WHERE TRUE; SELECT '1'",
        "SELECT 1 # '\n; DELETE FROM d.t WHERE TRUE",
        "/* /* */ ' */ DELETE FROM t -- '",
        "SELECT a$b$ FROM t; DELETE FROM t",
        "SELECT $a1$'$a1$; DELETE FROM t; SELECT '1'",
        "SELECT 1--1; DELETE FROM t",
    ],
)
def test_guard_refuses_writes_and_hidden_statements(mod: Any, sql: str) -> None:
    with pytest.raises(mod.UsageError):
        mod.check_read_only(sql)


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1;;", "SELECT 1"),
        ("SELECT 1; -- done\n", "SELECT 1"),
        ("SELECT * FROM t -- latest", "SELECT * FROM t"),
        ("SELECT 1\n-- end of query\n", "SELECT 1"),
    ],
)
def test_trailing_semicolons_and_comments_are_stripped(
    mod: Any, sql: str, expected: str
) -> None:
    assert mod.check_read_only(sql) == expected


def test_analyze_write_flags_destructive_statements(mod: Any) -> None:
    count, warnings = mod.analyze_write(
        "DELETE FROM a; UPDATE b SET x = (SELECT y FROM s WHERE id = 1); "
        "DROP TABLE c; TRUNCATE d; CREATE OR REPLACE TABLE e (x INT); "
        "INSERT OVERWRITE TABLE f SELECT 1; "
        "MERGE INTO g USING h ON g.id = h.id WHEN MATCHED THEN DELETE; "
        "WITH x AS (SELECT 1) DELETE FROM i; EXPLAIN ANALYZE DELETE FROM j; SELECT 1"
    )
    assert count == 10
    text = " ".join(warnings)
    for expected in (
        "DELETE without WHERE",
        "UPDATE without WHERE",
        "DROP",
        "TRUNCATE",
        "CREATE OR REPLACE",
        "INSERT OVERWRITE",
        "MERGE",
        "EXPLAIN ANALYZE runs",
        "only reads",
    ):
        assert expected in text


@pytest.mark.parametrize(
    ("name", "driver", "quoted"),
    [
        ("orders", "snowflake", '"orders"'),
        ('"My_View"', "datasphere-v1", '"My_View"'),
        ('a"b', "postgres", '"a""b"'),
        ("orders", "databricks-v1", "`orders`"),
        ("t; DELETE FROM t", "mysql", "`t; DELETE FROM t`"),
    ],
)
def test_quote_identifier(mod: Any, name: str, driver: str, quoted: str) -> None:
    assert mod.quote_identifier(name, driver) == quoted


# --------------------------------------------------------------------------- #
# Read routes and fallback
# --------------------------------------------------------------------------- #


def test_query_uses_preview_query_route(mod: Any, api: Any, capsys: Any) -> None:
    calls = api({("POST", "/previewQuery/"): PREVIEW})
    code = mod.main(["query", "--datastore-id", DS, "--sql", "SELECT id, name FROM t;"])
    assert code == 0
    assert routes_of(calls) == ["previewQuery"]
    assert calls[0]["body"] == {"sql": "SELECT id, name FROM t", "maxRows": 100}
    out = capsys.readouterr().out
    assert "# route: previewQuery" in out and "id INTEGER" in out and "NULL" in out


def test_query_falls_back_when_feature_gated(mod: Any, api: Any, capsys: Any) -> None:
    calls = api(
        {
            ("POST", "/previewQuery/"): mod.ApiError(403, GATED),
            ("GET", f"dataconnection:{DS}/"): ASSOCIATIONS,
            ("POST", "/verifySQL/"): {"columns": ["x"], "records": [["1"]]},
        }
    )
    code = mod.main(
        ["query", "--datastore-id", DS, "--sql", "SELECT 1 AS x", "--max-rows", "5000"]
    )
    assert code == 0
    assert routes_of(calls) == ["previewQuery", f"dataconnection:{DS}", "verifySQL"]
    assert calls[-1]["body"] == {
        "query": "SELECT 1 AS x",
        "maxRows": 999,
        "credentialId": CRED,
    }
    out = capsys.readouterr().out
    assert "verifySQL (legacy)" in out and "not enabled for this account" in out


def test_query_falls_back_on_seat_license_403(mod: Any, api: Any) -> None:
    calls = api(
        {
            ("POST", "/previewQuery/"): mod.ApiError(
                403, "Access denied due to seat license restrictions"
            ),
            ("POST", "/verifySQL/"): {"columns": ["x"], "records": []},
        }
    )
    args = ["query", "--datastore-id", DS, "--credential-id", CRED, "--sql", "SELECT 1"]
    assert mod.main(args) == 0
    assert routes_of(calls)[-1] == "verifySQL"


def test_query_falls_back_only_for_a_json_route_404(mod: Any, api: Any) -> None:
    calls = api(
        {
            ("POST", "/previewQuery/"): mod.ApiError(404, "Not Found"),
            ("POST", "/verifySQL/"): {"columns": ["x"], "records": []},
        }
    )
    args = ["query", "--datastore-id", DS, "--credential-id", CRED, "--sql", "SELECT 1"]
    assert mod.main(args) == 0
    assert calls[-1]["body"]["credentialId"] == CRED

    calls = api({("POST", "/previewQuery/"): mod.ApiError(404, "Not Found", False)})
    assert mod.main(args) == 2
    assert routes_of(calls) == ["previewQuery"]


def test_query_does_not_fall_back_on_database_errors(
    mod: Any, api: Any, capsys: Any
) -> None:
    denied = "You do not have the required permissions. Details: bad password"
    calls = api({("POST", "/previewQuery/"): mod.ApiError(403, denied)})
    assert mod.main(["query", "--datastore-id", DS, "--sql", "SELECT 1"]) == 2
    assert routes_of(calls) == ["previewQuery"]
    assert "rejected the credential" in capsys.readouterr().err


def test_route_new_never_falls_back(mod: Any, api: Any) -> None:
    calls = api({("POST", "/previewQuery/"): mod.ApiError(403, GATED)})
    args = ["query", "--datastore-id", DS, "--sql", "SELECT 1", "--route", "new"]
    assert mod.main(args) == 2
    assert routes_of(calls) == ["previewQuery"]


def test_bind_parameters(mod: Any, api: Any) -> None:
    calls = api(
        {
            ("GET", f"externalDataStores/{DS}/"): STORE,
            ("POST", "/previewQuery/"): PREVIEW,
        }
    )
    args = ["query", "--datastore-id", DS, "--sql", "SELECT ?", "--bind", "[1, null]"]
    assert mod.main(args) == 0
    assert calls[-1]["body"]["bindParams"] == [1, None]

    calls = api({("POST", "/previewQuery/"): PREVIEW})
    assert mod.main([*args[:-1], "[]"]) == 0
    assert "bindParams" not in calls[-1]["body"]


def test_bind_parameters_are_refused_for_legacy_drivers(mod: Any, api: Any) -> None:
    legacy = {**STORE, "type": "jdbc", "driverClassType": "postgres"}
    calls = api({("GET", f"externalDataStores/{DS}/"): legacy})
    args = ["query", "--datastore-id", DS, "--sql", "SELECT ?", "--bind", '["a"]']
    assert mod.main(args) == 1
    assert all(c["method"] == "GET" for c in calls)
    assert mod.main([*args, "--route", "legacy"]) == 1


def test_bind_parameters_cannot_fall_back(mod: Any, api: Any) -> None:
    api(
        {
            ("GET", f"externalDataStores/{DS}/"): STORE,
            ("POST", "/previewQuery/"): mod.ApiError(403, GATED),
        }
    )
    args = ["query", "--datastore-id", DS, "--sql", "SELECT ?", "--bind", '["a"]']
    assert mod.main(args) == 5


def test_preview_fallback_quotes_the_table_name(mod: Any, api: Any) -> None:
    calls = api(
        {
            ("POST", "/preview/"): mod.ApiError(403, GATED),
            ("GET", f"externalDataStores/{DS}/"): {
                **STORE,
                "driverClassType": "snowflake",
            },
            ("GET", f"dataconnection:{DS}/"): ASSOCIATIONS,
            ("POST", "/verifySQL/"): PREVIEW,
        }
    )
    code = mod.main(
        [
            "preview",
            "--datastore-id",
            DS,
            "--schema",
            "S",
            "--table",
            "t; DELETE FROM t",
        ]
    )
    assert code == 0
    assert calls[0]["body"] == {
        "table": "t; DELETE FROM t",
        "maxRows": 20,
        "schema": "S",
    }
    assert calls[-1]["body"]["query"] == 'SELECT * FROM "S"."t; DELETE FROM t"'


def test_legacy_route_without_any_credential_is_a_usage_error(
    mod: Any, api: Any
) -> None:
    api({("GET", f"dataconnection:{DS}/"): {"data": []}})
    args = ["query", "--datastore-id", DS, "--sql", "SELECT 1", "--route", "legacy"]
    assert mod.main(args) == 1


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #


def plan_token_from(output: str) -> str:
    match = re.search(r"--confirm (\w+)", output)
    assert match, output
    return match.group(1)


def write_routes(response: Any) -> Routes:
    return {
        ("GET", f"externalDataStores/{DS}/"): STORE,
        ("GET", f"dataconnection:{DS}/"): ASSOCIATIONS,
        ("POST", "/executeUpdate/"): response,
    }


def test_plan_then_execute_with_token(mod: Any, api: Any, capsys: Any) -> None:
    calls = api(write_routes({"message": "OK"}))
    args = ["--datastore-id", DS, "--sql", "UPDATE t SET a = ?", "--bind", '["x"]']
    assert mod.main(["plan", *args]) == 0
    out = capsys.readouterr().out
    assert "WRITE PLAN (nothing has run)" in out and "UPDATE without WHERE" in out
    assert "default credential 'svc'" in out and 'binds      : ["x"]' in out
    assert "Databricks does not wrap" in out
    assert "Confirm it exists and is a table, not a view" in out
    token = plan_token_from(out)
    assert not any(c["method"] == "POST" for c in calls)

    assert mod.main(["execute", *args, "--confirm", "0000000000"]) == 3
    assert "does not match this plan" in capsys.readouterr().out
    changed = [*args[:-1], '["y"]']
    assert mod.main(["execute", *changed, "--confirm", token]) == 3

    assert mod.main(["execute", *args, "--confirm", token]) == 0
    posts = [c for c in calls if c["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["body"] == {"sql": "UPDATE t SET a = ?", "bindParams": ["x"]}
    assert posts[0]["retries"] == 0


def confirmed(mod: Any, api: Any, capsys: Any, response: Any) -> int:
    api(write_routes(response))
    args = ["--datastore-id", DS, "--sql", "DELETE FROM t WHERE id = 1"]
    assert mod.main(["plan", *args]) == 0
    token = plan_token_from(capsys.readouterr().out)
    return int(mod.main(["execute", *args, "--confirm", token]))


def test_execute_failure_message_exits_4(mod: Any, api: Any, capsys: Any) -> None:
    assert confirmed(mod, api, capsys, {"message": "constraint violated"}) == 4


@pytest.mark.parametrize(
    "error",
    [
        (403, GATED),
        (409, "SQL execution is not supported for this data store."),
        (404, "Not Found"),
    ],
)
def test_execute_unavailable_exits_5(
    mod: Any, api: Any, capsys: Any, error: tuple[int, str]
) -> None:
    assert confirmed(mod, api, capsys, mod.ApiError(*error)) == 5


@pytest.mark.parametrize("status", [408, 502, 504])
def test_execute_unknown_outcome_on_timeouts_and_5xx(
    mod: Any, api: Any, capsys: Any, status: int
) -> None:
    assert confirmed(mod, api, capsys, mod.ApiError(status, "upstream")) == 2
    assert "may or may not have run" in capsys.readouterr().err


def test_plan_refuses_connections_without_write_support(
    mod: Any, api: Any, capsys: Any
) -> None:
    legacy = {**STORE, "type": "jdbc", "driverClassType": "postgres"}
    calls = api(
        {
            ("GET", f"externalDataStores/{DS}/"): legacy,
            ("GET", f"dataconnection:{DS}/"): ASSOCIATIONS,
        }
    )
    args = ["--datastore-id", DS, "--sql", "INSERT INTO t VALUES (1)"]
    assert mod.main(["plan", *args]) == 5
    out = capsys.readouterr().out
    assert "CANNOT WRITE THROUGH DATAROBOT" in out and "approval" not in out
    assert "datarobot-connectivity-jdbc-sql" in out
    assert mod.main(["execute", *args, "--confirm", "0000000000"]) == 5
    assert not any(c["method"] == "POST" for c in calls)


def test_routes_reports_availability_without_sending_sql(
    mod: Any, api: Any, capsys: Any
) -> None:
    calls = api(
        {
            ("GET", f"externalDataStores/{DS}/"): STORE,
            ("POST", "/previewQuery/"): mod.ApiError(422, "Invalid field data"),
            ("POST", "/preview/"): mod.ApiError(
                403, "Access denied due to seat license restrictions"
            ),
            ("POST", "/executeUpdate/"): mod.ApiError(403, GATED),
        }
    )
    assert mod.main(["routes", "--datastore-id", DS]) == 0
    assert [c.get("body") for c in calls if c["method"] == "POST"] == [{}, {}, {}]
    out = capsys.readouterr().out
    assert "available" in out and "not in your seat license" in out
    assert "not enabled for this account" in out and "no SQL ran" in out
    assert "driver databricks-v1, sql = read (fast) + write" in out


def test_routes_says_when_the_connection_cannot_write(
    mod: Any, api: Any, capsys: Any
) -> None:
    hana = {**STORE, "type": "jdbc", "driverClassType": "sap"}
    api(
        {
            ("GET", f"externalDataStores/{DS}/"): hana,
            ("POST", "/"): mod.ApiError(422, "Invalid field data"),
        }
    )
    assert mod.main(["routes", "--datastore-id", DS]) == 0
    out = capsys.readouterr().out
    assert "available to your account, but driver sap cannot write" in out
    assert "sql = read (legacy)" in out


# --------------------------------------------------------------------------- #
# CLI, config, output
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "argv",
    [
        ["query", "--sql", "SELECT 1"],
        ["execute", "--datastore-id", DS, "--sql", "DELETE FROM t WHERE id = 1"],
        ["query", "--datastore-id", "not-an-id", "--sql", "SELECT 1"],
        ["query", "--datastore-id", DS, "--sql", "SELECT 1", "--max-rows", "abc"],
        ["query", "--datastore-id", DS, "--sql", "SELECT 1", "--show", "-1"],
        [
            "query",
            "--datastore-id",
            DS,
            "--sql",
            "SELECT 1",
            "--out",
            "/no/such/dir/x.csv",
        ],
    ],
)
def test_usage_errors_exit_1(mod: Any, api: Any, argv: list[str]) -> None:
    calls = api({})
    with pytest.raises(SystemExit) as raised:
        code = mod.main(argv)
        raise SystemExit(code)
    assert raised.value.code == 1
    assert calls == []


def test_config_pairs(
    mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "datarobot" / "drconfig.yaml"
    config.parent.mkdir()
    config.write_text(
        "endpoint: 'https://dr.example.test'  # comment\ntoken: \"abc\"\n"
        "llm_gateway:\n  token: NESTED\ntoken: SECOND\n",
        encoding="utf-8",
    )
    for name in ("DATAROBOT_ENDPOINT", "DATAROBOT_API_TOKEN", "DATAROBOT_CONFIG_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert mod.load_config() == ("https://dr.example.test/api/v2", "abc")

    monkeypatch.setenv("DATAROBOT_ENDPOINT", "https://other.example.test/api/v2")
    with pytest.raises(mod.UsageError, match="DATAROBOT_API_TOKEN is not set"):
        mod.load_config()

    monkeypatch.setenv("DATAROBOT_API_TOKEN", "env-token")
    monkeypatch.setenv("DATAROBOT_ENDPOINT", "dr.example.test/api/v2")
    with pytest.raises(mod.UsageError, match="full URL"):
        mod.load_config()


def test_csv_mode_keeps_notes_on_stderr(mod: Any, api: Any, capsys: Any) -> None:
    api({("POST", "/previewQuery/"): PREVIEW})
    args = ["query", "--datastore-id", DS, "--sql", "SELECT 1", "--max-rows", "2"]
    assert mod.main([*args, "--format", "csv"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "id,name\n1,a\n2,\n"
    assert (
        "# route: previewQuery" in captured.err and "probably truncated" in captured.err
    )


def test_json_output_and_out_file(
    mod: Any, api: Any, tmp_path: Path, capsys: Any
) -> None:
    api({("POST", "/previewQuery/"): PREVIEW})
    args = ["query", "--datastore-id", DS, "--sql", "SELECT 1", "--max-rows", "2"]
    mod.main([*args, "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["possiblyTruncated"] is True and payload["records"][1] == ["2", None]

    target = tmp_path / "rows.csv"
    assert mod.main([*args, "--out", str(target), "--show", "1"]) == 0
    assert target.read_text(encoding="utf-8") == "id,name\n1,a\n2,\n"
    printed = capsys.readouterr().out
    assert "# wrote all 2 rows" in printed and "more row" not in printed

    assert mod.main([*args, "--show", "1"]) == 0
    assert "# ... 1 more row (use --out" in capsys.readouterr().out


def test_discovery_lists_print_more_rows_by_default(
    mod: Any, api: Any, capsys: Any
) -> None:
    tables = {"tables": [{"schema": "s", "name": f"t{i:02}"} for i in range(30)]}
    api(
        {
            ("POST", "/tables/"): tables,
            ("POST", "/previewQuery/"): {**PREVIEW, "records": [["1", "a"]] * 30},
            ("GET", f"dataconnection:{DS}/"): ASSOCIATIONS,
        }
    )
    assert mod.main(["tables", "--datastore-id", DS]) == 0
    out = capsys.readouterr().out
    assert "t29" in out and "more row" not in out
    assert mod.main(["query", "--datastore-id", DS, "--sql", "SELECT 1"]) == 0
    assert "# ... 10 more rows" in capsys.readouterr().out


def test_discovery_errors_point_at_what_exists(mod: Any, api: Any, capsys: Any) -> None:
    missing = mod.ApiError(400, "invalid table name: Could not find table/view T")
    api(
        {
            ("POST", "/columns/"): missing,
            ("GET", f"dataconnection:{DS}/"): ASSOCIATIONS,
        }
    )
    argv = ["columns", "--datastore-id", DS, "--schema", "S", "--table", "T"]
    assert mod.main(argv) == 2
    err = capsys.readouterr().err
    assert "List what exists with `schemas` and `tables --schema S`" in err
    assert "check that the objects exist" not in err


def test_unwritable_out_file_is_not_a_success(
    mod: Any, api: Any, tmp_path: Path, capsys: Any
) -> None:
    api({("POST", "/previewQuery/"): PREVIEW})
    out = tmp_path / "rows.csv"
    out.mkdir()  # the directory exists, but the file cannot be written
    args = ["query", "--datastore-id", DS, "--sql", "SELECT 1", "--out", str(out)]
    assert mod.main(args) == 1
    captured = capsys.readouterr()
    assert "could not write --out" in captured.err
    assert "id" in captured.out and "wrote all" not in captured.out


@pytest.mark.parametrize(
    ("driver", "sql", "sent", "looked_up"),
    [
        ("mysql", "SELECT 1 AS ok # note", "SELECT 1 AS ok", True),
        ("mysql", "SELECT 5 --1", "SELECT 5 --1", True),
        ("bigquery-v1", "SELECT 1 AS ok --a\n# b", "SELECT 1 AS ok", True),
        ("postgres", "SELECT 5 # 3", "SELECT 5 # 3", True),
        ("postgres", "SELECT 1 AS ok -- note;", "SELECT 1 AS ok", False),
    ],
)
def test_trailing_comments_follow_the_connection_dialect(
    mod: Any, api: Any, driver: str, sql: str, sent: str, looked_up: bool
) -> None:
    store = {**STORE, "driverClassType": driver}
    calls = api(
        {
            ("GET", f"externalDataStores/{DS}/"): store,
            ("POST", "/previewQuery/"): PREVIEW,
        }
    )
    assert mod.main(["query", "--datastore-id", DS, "--sql", sql]) == 0
    assert calls[-1]["body"]["sql"] == sent
    assert (calls[0]["method"] == "GET") is looked_up


def test_preview_samples_are_not_reported_as_truncated(
    mod: Any, api: Any, capsys: Any
) -> None:
    api({("POST", "/preview/"): PREVIEW})
    args = ["preview", "--datastore-id", DS, "--table", "T", "--max-rows", "2"]
    assert mod.main(args) == 0
    out = capsys.readouterr().out
    assert "preview shows the first 2 rows only" in out and "truncated" not in out


def test_discovery_explains_empty_and_filtered_results(
    mod: Any, api: Any, capsys: Any
) -> None:
    tables = {
        "tables": [{"schema": "S", "name": "orders"}, {"schema": "S", "name": "x"}]
    }
    api(
        {
            ("GET", f"dataconnection:{DS}/"): ASSOCIATIONS,
            ("POST", "/tables/"): tables,
            ("POST", "/columns/"): {"columns": []},
        }
    )
    assert mod.main(["tables", "--datastore-id", DS, "--like", "ORD"]) == 0
    assert "1 of 2 names contain 'ORD'" in capsys.readouterr().out
    assert mod.main(["columns", "--datastore-id", DS, "--table", "missing"]) == 0
    assert "no rows: discovery lists only objects" in capsys.readouterr().out


def test_datastores_lists_all_types_with_capabilities(
    mod: Any, api: Any, capsys: Any
) -> None:
    stores = {
        "data": [
            {
                "id": "1",
                "canonicalName": "sf",
                "type": "jdbc",
                "driverClassType": "snowflake",
            },
            {
                "id": "2",
                "canonicalName": "pg",
                "type": "jdbc",
                "driverClassType": "postgres",
            },
            {
                "id": "3",
                "canonicalName": "s3",
                "type": "dr-connector-v1",
                "driverClassType": "native-s3",
            },
        ]
    }
    calls = api({("GET", "externalDataStores/"): stores})
    assert mod.main(["datastores"]) == 0
    assert calls[0]["params"] == {"type": "all"}
    out = capsys.readouterr().out
    assert "read (fast) + write" in out and "read (legacy)" in out and "no SQL" in out
    assert "role = your access" in out and "these are all 3 connections" in out


# --------------------------------------------------------------------------- #
# Real HTTP layer against a local server
# --------------------------------------------------------------------------- #

Reply = tuple[int, bytes, dict[str, str]]


@pytest.fixture
def server(
    env: pytest.MonkeyPatch,
) -> Iterator[Callable[[list[Reply]], list[dict[str, Any]]]]:
    """Local HTTP server that answers with a scripted sequence of replies."""
    replies: list[Reply] = []
    seen: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return None

        def _reply(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode() if length else ""
            seen.append(
                {
                    "method": self.command,
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

        do_GET = do_POST = _reply

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    env.setenv("DATAROBOT_ENDPOINT", f"http://127.0.0.1:{httpd.server_port}/api/v2")

    def script(sequence: list[Reply]) -> list[dict[str, Any]]:
        replies[:] = sequence
        seen.clear()
        return seen

    yield script
    httpd.shutdown()


def j(payload: Any) -> bytes:
    return json.dumps(payload).encode()


def test_http_reads_retry_once_and_send_the_token(mod: Any, server: Any) -> None:
    seen = server(
        [(503, j({"message": "busy"}), {"Retry-After": "1"}), (200, j(PREVIEW), {})]
    )
    assert mod.main(["query", "--datastore-id", DS, "--sql", "SELECT 1"]) == 0
    assert len(seen) == 2
    assert seen[0]["auth"] == f"Bearer {TOKEN}"
    assert seen[0]["path"] == f"/api/v2/externalDataStores/{DS}/previewQuery/"


def http_write(
    mod: Any, server: Any, capsys: Any, reply: Reply
) -> tuple[int, list[dict[str, Any]]]:
    store, assoc = (200, j(STORE), {}), (200, j(ASSOCIATIONS), {})
    args = ["--datastore-id", DS, "--sql", "DELETE FROM t WHERE id = 1"]
    server([store, assoc])
    assert mod.main(["plan", *args]) == 0
    token = plan_token_from(capsys.readouterr().out)
    seen = server([store, assoc, reply])
    return int(mod.main(["execute", *args, "--confirm", token])), seen


def test_http_writes_are_never_retried(mod: Any, server: Any, capsys: Any) -> None:
    code, seen = http_write(mod, server, capsys, (503, j({"message": "busy"}), {}))
    assert code == 2
    assert [s["path"].split("/")[-2] for s in seen if s["method"] == "POST"] == [
        "executeUpdate"
    ]
    assert "may or may not have run" in capsys.readouterr().err


def test_http_unreadable_write_response_is_an_unknown_outcome(
    mod: Any, server: Any, capsys: Any
) -> None:
    code, _ = http_write(mod, server, capsys, (200, b"<html>login</html>", {}))
    assert code == 2
    assert "may or may not have run" in capsys.readouterr().err


def test_http_redirects_are_not_followed(mod: Any, server: Any, capsys: Any) -> None:
    seen = server([(302, b"", {"Location": "http://127.0.0.1:9/steal"})])
    assert mod.main(["query", "--datastore-id", DS, "--sql", "SELECT 1"]) == 2
    assert len(seen) == 1
    captured = capsys.readouterr()
    assert "redirect" in captured.err and TOKEN not in captured.out + captured.err


def test_http_401_never_prints_the_token(mod: Any, server: Any, capsys: Any) -> None:
    server([(401, b"", {})])
    assert mod.main(["datastores"]) == 2
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
    assert "datarobot-setup" in captured.err
