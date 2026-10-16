#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Query, explore, and update databases through DataRobot data connections.

Commands (run ``python datastore_sql.py <command> -h`` for options):

  datastores    List data connections and the SQL each one supports
  credentials   List credentials stored for a data connection (marks the default)
  schemas       List catalogs and schemas
  tables        List tables and views
  columns       List the columns of a table
  preview       Preview rows of a table
  query         Run one read-only SQL query
  routes        Check which newer routes this account can use (sends no SQL)
  plan          Show the plan and confirm token for DML/DDL (changes nothing)
  execute       Run DML/DDL; needs the --confirm token from `plan`

Auth: DATAROBOT_ENDPOINT (ends in /api/v2) and DATAROBOT_API_TOKEN together, or
both keys in drconfig.yaml (DATAROBOT_CONFIG_FILE, else
$XDG_CONFIG_HOME/datarobot/drconfig.yaml, else ~/.config/datarobot/drconfig.yaml).
Standard library only; Python 3.9+.

Exit codes: 0 ok, 1 usage or config error, 2 API error or unknown write
outcome, 3 --confirm token does not match the current plan, 4 the database
reported a write failure, 5 route or operation unavailable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import IO, Any, NoReturn

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_API = 2
EXIT_CONFIRM = 3
EXIT_WRITE_FAILED = 4
EXIT_UNAVAILABLE = 5

# The server stops previews, queries, writes, and metadata calls after 300 s.
SQL_TIMEOUT = 330
META_TIMEOUT = 330
MAX_ROWS = 10_000
LEGACY_MAX_ROWS = 999  # upper bound of /verifySQL/
MAX_BIND_PARAMS = 100
USER_AGENT = "datarobot-agent-skills/datarobot-connectivity-datastore-sql"
OBJECT_ID = re.compile(r"[0-9a-fA-F]{24}")

# driverClassType values served by DataRobot's native connector path.
FAST_WRITE_DRIVERS = frozenset(
    {"snowflake", "bigquery-v1", "databricks-v1", "datasphere-v1", "trino-v1"}
)
FAST_READ_ONLY_DRIVERS = frozenset({"salesforce-v1"})
SQL_STORE_TYPES = frozenset({"jdbc", "dr-database-v1"})
BACKTICK_DRIVERS = ("mysql", "bigquery", "databricks", "native-databricks")
TRANSACTION_NOTES = {
    "snowflake": "Snowflake runs all statements of one request in a single "
    "transaction.",
    "databricks-v1": "Databricks does not wrap the request in a transaction: "
    "statements that ran before a failure stay applied.",
    "trino-v1": "Trino writes run in autocommit mode; send one statement per request.",
}
DEFAULT_TRANSACTION_NOTE = (
    "Atomicity is connector-specific; prefer one statement per request."
)

# `query` and `preview` accept only statements that start with one of these...
READ_STARTS = frozenset(
    ["SELECT", "WITH", "VALUES", "TABLE", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"]
)
# ...and contain none of these words anywhere outside quotes and comments.
WRITE_WORDS = frozenset(["INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "INTO"])
DML_WORDS = frozenset(["INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT"])


class UsageError(Exception):
    """Bad arguments or configuration."""


class RouteUnavailable(Exception):
    """The route or operation is not available for this account or connection."""


class TransportError(Exception):
    """No usable HTTP response: network failure, timeout, or unreadable body."""


class ApiError(Exception):
    """A non-2xx response from DataRobot."""

    def __init__(self, status: int, message: str, from_body: bool = True) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message
        self.from_body = from_body

    @property
    def feature_gated(self) -> bool:
        """403 because the account lacks the feature or seat for this route."""
        return self.status == 403 and (
            "Future Public API" in self.message or "seat license" in self.message
        )

    @property
    def route_missing(self) -> bool:
        """A JSON 404 for the route itself (older DataRobot), not for a resource."""
        return (
            self.status == 404
            and self.from_body
            and self.message.strip() == "Not Found"
        )


# --------------------------------------------------------------------------- #
# Configuration and HTTP
# --------------------------------------------------------------------------- #


def config_path() -> Path:
    explicit = os.environ.get("DATAROBOT_CONFIG_FILE")
    if explicit:
        return Path(explicit)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "datarobot" / "drconfig.yaml"


def _read_config_file(path: Path) -> dict[str, str]:
    """Read top-level `endpoint` and `token` from a drconfig.yaml-style file."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        match = re.match(r"(endpoint|token)\s*:\s*(\S.*?)\s*$", line)
        if match and match.group(1) not in values:
            value = re.sub(r"\s+#.*$", "", match.group(2))
            values[match.group(1)] = value.strip().strip("'\"")
    return values


def load_config() -> tuple[str, str]:
    """Endpoint and token always come as a pair from one source."""
    env_endpoint = os.environ.get("DATAROBOT_ENDPOINT", "").strip()
    env_token = os.environ.get("DATAROBOT_API_TOKEN", "").strip()
    path = config_path()
    if env_endpoint or env_token:
        if not (env_endpoint and env_token):
            missing = "DATAROBOT_API_TOKEN" if env_endpoint else "DATAROBOT_ENDPOINT"
            raise UsageError(
                f"{missing} is not set. Set both DATAROBOT_ENDPOINT and "
                f"DATAROBOT_API_TOKEN, or neither to use {path}."
            )
        endpoint, token = env_endpoint, env_token
    else:
        config = _read_config_file(path)
        endpoint, token = config.get("endpoint", ""), config.get("token", "")
        if not (endpoint and token):
            raise UsageError(
                "DataRobot credentials not found. Set DATAROBOT_ENDPOINT (ending "
                "in /api/v2) and DATAROBOT_API_TOKEN, or run the datarobot-setup "
                "skill."
            )
    endpoint = endpoint.rstrip("/")
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise UsageError(
            f"DATAROBOT_ENDPOINT must be a full URL such as "
            f"https://app.datarobot.com/api/v2, got {endpoint!r}."
        )
    if parsed.path in ("", "/"):
        endpoint += "/api/v2"
    return endpoint, token


def _ssl_context() -> ssl.SSLContext | None:
    verify = os.environ.get("DATAROBOT_SSL_VERIFY", "").strip()
    if verify.lower() in ("false", "0", "no", "off"):
        # Opt-in through DATAROBOT_SSL_VERIFY=false for clusters with a private CA.
        return ssl._create_unverified_context()  # noqa: S323
    if verify and verify.lower() not in ("true", "1", "yes", "on"):
        return ssl.create_default_context(cafile=verify)
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: they would carry the API token to another URL."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


def _error_message(exc: urllib.error.HTTPError) -> tuple[str, bool]:
    """Return (message, whether it came from a JSON body)."""
    try:
        text = exc.read().decode("utf-8", "replace").strip()
    except (OSError, http.client.HTTPException):
        text = ""
    if not text:
        return str(exc.reason or "no response body"), False
    try:
        payload = json.loads(text)
    except ValueError:
        return text[:500], False
    if not isinstance(payload, dict):
        return text[:500], False
    message = str(payload.get("message") or payload.get("detail") or "").strip()
    errors = payload.get("errors")
    if isinstance(errors, dict) and errors:
        details = "; ".join(f"{key}: {value}" for key, value in errors.items())
        message = f"{message} ({details})" if message else details
    return message or text[:500], True


def _retry_after(exc: urllib.error.HTTPError) -> float:
    header = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return min(max(float(header), 1.0), 30.0) if header else 2.0
    except ValueError:
        return 2.0


class DataRobotClient:
    """Minimal JSON client. It never retries unless asked to (writes never are)."""

    def __init__(self, endpoint: str, token: str) -> None:
        self.endpoint = endpoint
        self._token = token
        handlers: list[urllib.request.BaseHandler] = [_NoRedirect()]
        context = _ssl_context()
        if context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=context))
        self._opener = urllib.request.build_opener(*handlers)

    def call(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        timeout: float = META_TIMEOUT,
        retries: int = 0,
    ) -> Any:
        url = f"{self.endpoint}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(retries + 1):
            request = urllib.request.Request(
                url, data=data, headers=headers, method=method
            )
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    raw = response.read()
                return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 502, 503) and attempt < retries:
                    time.sleep(_retry_after(exc))
                    continue
                raise ApiError(exc.code, *_error_message(exc)) from None
            except (http.client.HTTPException, ValueError) as exc:
                raise TransportError(
                    f"unreadable response from DataRobot ({type(exc).__name__})"
                ) from None
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                reason = getattr(exc, "reason", None) or exc
                raise TransportError(str(reason)) from None
        raise TransportError("request was not sent")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


# --------------------------------------------------------------------------- #
# SQL helpers. The SQL is always sent verbatim; these checks only decide whether
# the script sends it, and what the dry-run plan warns about.
# --------------------------------------------------------------------------- #


class UnterminatedSQL(Exception):
    """A quote or comment does not end under a given lexing variant."""


@dataclass(frozen=True)
class Lexing:
    """One way a SQL dialect may lex quotes and comments."""

    backslash_escapes: bool = False  # MySQL, BigQuery, Databricks
    mysql_comments: bool = False  # '#' comments; '--' needs a following space
    nested_comments: bool = False  # PostgreSQL, Databricks
    dollar_quotes: bool = True  # PostgreSQL, Snowflake


STANDARD = Lexing()
VARIANTS = [Lexing(*flags) for flags in product((False, True), repeat=4)]


def lexings_for(driver: str) -> tuple[Lexing, ...]:
    """How the connection's database lexes SQL; BigQuery takes '#' and any '--'."""
    if driver.startswith("mysql"):
        return (
            Lexing(backslash_escapes=True, mysql_comments=True, dollar_quotes=False),
        )
    if driver.startswith("bigquery"):
        return (
            Lexing(backslash_escapes=True, mysql_comments=True, dollar_quotes=False),
            Lexing(backslash_escapes=True, dollar_quotes=False),
        )
    if driver.startswith(("databricks", "native-databricks")):
        return (
            Lexing(backslash_escapes=True, nested_comments=True, dollar_quotes=False),
        )
    if driver.startswith("postgres"):
        return (Lexing(nested_comments=True),)
    return (STANDARD,)


def mask_sql(sql: str, lexing: Lexing = STANDARD) -> str:
    """Blank out comments and quoted text, keeping every character position."""
    out = list(sql)
    i, n = 0, len(sql)

    def blank(start: int, end: int) -> None:
        out[start:end] = " " * (end - start)

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        dash_comment = ch == "-" and nxt == "-"
        if dash_comment and lexing.mysql_comments:
            dash_comment = i + 2 >= n or sql[i + 2].isspace()
        if dash_comment or (lexing.mysql_comments and ch == "#"):
            end = sql.find("\n", i)
            end = n if end == -1 else end
            blank(i, end)
            i = end
        elif ch == "/" and nxt == "*":
            depth, j = 1, i + 2
            while j < n and depth:
                if lexing.nested_comments and sql.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif sql.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            if depth:
                raise UnterminatedSQL("block comment")
            blank(i, j)
            i = j
        elif ch in "'\"`":
            j = i + 1
            while True:
                if j >= n:
                    raise UnterminatedSQL("quoted text")
                if lexing.backslash_escapes and sql[j] == "\\":
                    j += 2
                    continue
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:  # doubled quote escape
                        j += 2
                        continue
                    break
                j += 1
            blank(i + 1, j)
            i = j + 1
        elif (
            lexing.dollar_quotes
            and ch == "$"
            and (i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] in "_$"))
        ):
            match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", sql[i:])
            if not match:
                i += 1
                continue
            tag = match.group(0)
            close = sql.find(tag, i + len(tag))
            if close == -1:
                raise UnterminatedSQL("dollar-quoted text")
            blank(i, close + len(tag))
            i = close + len(tag)
        else:
            i += 1
    return "".join(out)


def _masked_variants(sql: str) -> list[str]:
    """Masked SQL under every lexing variant in which it is well formed."""
    masked = []
    for lexing in VARIANTS:
        try:
            masked.append(mask_sql(sql, lexing))
        except UnterminatedSQL:
            continue
    if not masked:
        raise UsageError("The SQL has an unterminated quote or comment.")
    return masked


def _words(masked: str) -> list[str]:
    return [w.upper() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", masked)]


def _statements(masked: str) -> list[str]:
    return [part for part in masked.split(";") if part.strip()]


def _top_level(masked: str) -> str:
    """Blank text inside parentheses, so subquery clauses are ignored."""
    out, depth = [], 0
    for ch in masked:
        if ch == "(":
            depth += 1
        out.append(ch if depth == 0 else " ")
        if ch == ")" and depth:
            depth -= 1
    return "".join(out)


def strip_trailing(sql: str, lexings: Sequence[Lexing] = (STANDARD,)) -> str:
    """Drop trailing comments and semicolons from a single statement.

    A row limit added after the SQL on the same line would be swallowed by a
    trailing comment the database recognizes.
    """
    text = sql.strip()
    while True:
        before = text
        for lexing in lexings:
            try:
                masked = mask_sql(text, lexing)
            except UnterminatedSQL:
                continue
            text = text[: len(masked.rstrip())]
            if text.endswith(";"):
                text = text[:-1].rstrip()
        if text == before:
            return text


def end_depends_on_dialect(sql: str) -> bool:
    """True when the SQL ends in text that is a comment in some dialects only."""
    ends = set()
    for lexing in VARIANTS:
        try:
            mask_sql(sql, lexing)
        except UnterminatedSQL:
            continue
        ends.add(strip_trailing(sql, (lexing,)))
    return len(ends) > 1


def plan_token(*parts: str) -> str:
    """Short fingerprint of an approved write; --confirm must repeat it."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:10]


def check_read_only(sql: str) -> str:
    """Return SQL ready for a read route, or raise UsageError.

    A keyword check cannot see side effects of functions (for example
    `SELECT pg_terminate_backend(...)`); only a read-only credential guarantees
    a read.
    """
    for masked in _masked_variants(sql):
        statements = _statements(masked)
        if not statements:
            raise UsageError("SQL is empty.")
        if len(statements) > 1:
            raise UsageError(
                "`query` runs exactly one statement. Run statements one at a "
                "time; use `execute` for writes."
            )
        words = _words(statements[0])
        keyword = words[0] if words else ""
        if keyword not in READ_STARTS:
            raise UsageError(
                f"`query` and `preview` only run reads (SELECT, WITH, VALUES, "
                f"SHOW, DESCRIBE, EXPLAIN); this SQL starts with "
                f"{keyword or 'no keyword'}. Use `execute`, which needs the "
                "user's explicit approval."
            )
        found = WRITE_WORDS & set(words)
        if found or (keyword == "EXPLAIN" and {"ANALYZE", "ANALYSE"} & set(words)):
            word = min(found) if found else "EXPLAIN ANALYZE"
            raise UsageError(
                f"`query` and `preview` are read-only and this SQL contains "
                f"{word}. Use `execute`, which needs the user's explicit approval."
            )
    return strip_trailing(sql)


def analyze_write(sql: str) -> tuple[int, list[str]]:
    """Count statements and collect advisory warnings for the dry-run plan."""
    try:
        masked = mask_sql(sql)
    except UnterminatedSQL:
        masked = _masked_variants(sql)[0]
    statements = _statements(masked)
    warnings: list[str] = []
    for statement in statements:
        words = _words(statement)
        found = set(words)
        keyword = words[0] if words else ""
        if keyword == "WITH":  # a CTE prelude before the real statement
            keyword = next((w for w in words if w in DML_WORDS), "WITH")
        top = _words(_top_level(statement))
        tail = top[top.index(keyword) + 1 :] if keyword in top else top
        if keyword == "DROP" or (keyword == "ALTER" and "DROP" in found):
            warnings.append("DROP permanently removes objects or columns.")
        elif keyword == "TRUNCATE":
            warnings.append("TRUNCATE removes every row of the table.")
        elif keyword == "CREATE" and "REPLACE" in found:
            warnings.append("CREATE OR REPLACE overwrites an existing object.")
        elif keyword == "INSERT" and "OVERWRITE" in found:
            warnings.append("INSERT OVERWRITE replaces the existing rows.")
        elif keyword == "MERGE" and "DELETE" in found:
            warnings.append("MERGE … DELETE removes matching rows.")
        elif keyword in ("DELETE", "UPDATE") and "WHERE" not in tail:
            warnings.append(f"{keyword} without WHERE changes every row.")
        elif keyword in ("GRANT", "REVOKE"):
            warnings.append(f"{keyword} changes database permissions.")
        elif keyword == "EXPLAIN" and {"ANALYZE", "ANALYSE"} & found:
            warnings.append("EXPLAIN ANALYZE runs the statement it explains.")
        elif keyword in READ_STARTS and not DML_WORDS & found:
            warnings.append(
                "A statement only reads data; `execute` returns no rows. "
                "Use `query` instead."
            )
    return len(statements), list(dict.fromkeys(warnings))


def read_sql(args: argparse.Namespace) -> str:
    if args.sql is not None:
        text = str(args.sql)
    elif args.sql_file == "-":
        text = sys.stdin.read()
    else:
        try:
            text = Path(args.sql_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"cannot read --sql-file: {exc}") from None
    if not text.strip():
        raise UsageError("SQL is empty.")
    return text


def parse_binds(raw: str | None) -> list[Any] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise UsageError(f"--bind must be a JSON list: {exc}") from None
    if not isinstance(value, list) or len(value) > MAX_BIND_PARAMS:
        raise UsageError(f"--bind must be a JSON list of at most {MAX_BIND_PARAMS}.")
    if any(isinstance(item, (dict, list)) for item in value):
        raise UsageError("--bind values must be strings, numbers, booleans, or null.")
    return value or None


def quote_identifier(name: str, driver: str) -> str:
    """Quote one identifier for the legacy route; strips quotes the user added."""
    for opener, closer in (('"', '"'), ("`", "`"), ("[", "]")):
        if len(name) >= 2 and name.startswith(opener) and name.endswith(closer):
            name = name[1:-1]
            break
    if driver.startswith(BACKTICK_DRIVERS):
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"'


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


@dataclass
class Result:
    columns: list[str]
    records: list[list[Any]]
    route: str = ""
    max_rows: int | None = None
    schema: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sample: bool = False  # a table preview: hitting maxRows is expected


def _cell(value: Any, width: int) -> str:
    if value is None:
        return "NULL"
    text = str(value).replace("\r", " ").replace("\n", "\\n").replace("\t", " ")
    return text if len(text) <= width else text[: max(width - 1, 1)] + "…"


def format_table(
    columns: Sequence[str], rows: Sequence[Sequence[Any]], width: int
) -> str:
    count = len(columns)
    grid = [[_cell(c, width) for c in columns]]
    for row in rows:
        cells = [_cell(v, width) for v in list(row)[:count]]
        grid.append(cells + [""] * (count - len(cells)))
    widths = [max(len(r[i]) for r in grid) for i in range(count)]
    lines = [
        " | ".join(text.ljust(w) for text, w in zip(row, widths)).rstrip()
        for row in grid
    ]
    lines.insert(1, "-+-".join("-" * w for w in widths))
    return "\n".join(lines)


def _type_label(entry: dict[str, Any]) -> str:
    data_type = str(entry.get("dataType") or "?")
    precision, scale = entry.get("precision"), entry.get("scale")
    if data_type.upper() in ("DECIMAL", "NUMERIC", "NUMBER") and precision not in (
        None,
        "",
    ):
        suffix = f",{scale}" if scale not in (None, "") else ""
        return f"{data_type}({precision}{suffix})"
    return data_type


def _to_csv(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(["" if v is None else v for v in row] for row in rows)
    return buffer.getvalue()


def _truncated(result: Result) -> bool:
    return bool(result.max_rows) and len(result.records) >= (result.max_rows or 0)


def _to_json(result: Result) -> str:
    payload: dict[str, Any] = {"columns": result.columns, "records": result.records}
    if result.route:
        payload = {
            "route": result.route,
            "maxRows": result.max_rows,
            "rowCount": len(result.records),
            "possiblyTruncated": _truncated(result),
            "notes": result.notes,
            "resultSchema": result.schema,
            **payload,
        }
    return json.dumps(payload, indent=2, default=str)


def _meta_lines(result: Result) -> list[str]:
    size = f"{len(result.records)} rows x {len(result.columns)} columns"
    if result.route:
        lines = [f"# route: {result.route} | {size} | maxRows {result.max_rows}"]
    else:
        lines = [f"# {size}"]
    if result.schema:
        types = ", ".join(f"{e.get('name')} {_type_label(e)}" for e in result.schema)
        lines.append(f"# types: {types}")
    lines += [f"# note: {note}" for note in result.notes]
    if _truncated(result) and result.sample:
        lines.append(f"# note: preview shows the first {result.max_rows} rows only")
    elif _truncated(result):
        advice = (
            "The legacy route returns at most 999 rows: narrow the query "
            "(WHERE/LIMIT/aggregate)."
            if result.route.startswith("verifySQL")
            else "Narrow the query (WHERE/LIMIT/aggregate) or raise --max-rows "
            f"(max {MAX_ROWS})."
        )
        lines.append(
            f"# warning: hit maxRows={result.max_rows}; the result is probably "
            f"truncated. {advice}"
        )
    return lines


def emit(result: Result, args: argparse.Namespace) -> int:
    """Print or save a result. Exit 1 when --out could not be written."""
    rows = result.records
    status = EXIT_OK
    if args.out:
        path = Path(args.out)
        as_json = path.suffix.lower() == ".json" or (
            args.format == "json" and path.suffix.lower() != ".csv"
        )
        try:
            path.write_text(
                _to_json(result) if as_json else _to_csv(result.columns, rows),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"error: could not write --out: {exc}", file=sys.stderr)
            args.out = None
            status = EXIT_USAGE
    if args.format == "json" and not args.out:
        print(_to_json(result))
        return status
    meta = _meta_lines(result)
    if args.format == "csv" and not args.out:
        for line in meta:
            print(line, file=sys.stderr)
        sys.stdout.write(_to_csv(result.columns, rows))
        return status
    for line in meta:
        print(line)
    if args.out:
        print(f"# wrote all {len(rows)} rows to {args.out}")
    if result.columns and (args.show or not args.out):
        print(format_table(result.columns, rows[: args.show], args.width))
    if len(rows) > args.show and not args.out:
        more = len(rows) - args.show
        print(
            f"# ... {more} more row{'s' if more > 1 else ''} (use --out FILE or --show N)"
        )
    return status


def preview_result(data: Any, route: str, max_rows: int, notes: list[str]) -> Result:
    payload = _as_dict(data)
    return Result(
        columns=[str(c) for c in _as_list(payload.get("columns"))],
        records=[_as_list(r) for r in _as_list(payload.get("records"))],
        route=route,
        max_rows=max_rows,
        schema=[_as_dict(s) for s in _as_list(payload.get("resultSchema"))],
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Connection helpers
# --------------------------------------------------------------------------- #


def sql_support(store: dict[str, Any]) -> str:
    store_type = str(store.get("type") or "")
    driver = str(store.get("driverClassType") or "")
    if store_type not in SQL_STORE_TYPES:
        return "no SQL (file/object connector)"
    if driver in FAST_WRITE_DRIVERS:
        return "read (fast) + write"
    if driver in FAST_READ_ONLY_DRIVERS:
        return "read (fast)"
    return "read (legacy)"


def get_store(client: DataRobotClient, datastore_id: str) -> dict[str, Any]:
    return _as_dict(client.call("GET", f"externalDataStores/{datastore_id}/"))


def credential_associations(
    client: DataRobotClient, datastore_id: str
) -> list[dict[str, Any]]:
    data = client.call(
        "GET",
        f"credentials/associations/dataconnection:{datastore_id}/",
        params={"orderBy": "-isDefault", "limit": "100"},
    )
    return [_as_dict(item) for item in _as_list(_as_dict(data).get("data"))]


def resolve_credential(
    client: DataRobotClient, datastore_id: str, explicit: str | None
) -> tuple[str | None, str]:
    """Return (credential id or None, human-readable label)."""
    if explicit:
        return explicit, f"credential {explicit}"
    for item in credential_associations(client, datastore_id):
        if item.get("isDefault"):
            return str(item.get("credentialId")), (
                f"default credential '{item.get('name')}' ({item.get('credentialId')})"
            )
    return None, "no default credential"


def require_credential(
    client: DataRobotClient, datastore_id: str, explicit: str | None
) -> str:
    credential_id, _ = resolve_credential(client, datastore_id, explicit)
    if not credential_id:
        raise UsageError(
            "This route needs a credential. Pass --credential-id (list them with "
            "`credentials`) or set a default credential for the connection in "
            "DataRobot."
        )
    return credential_id


def _fallback_note(primary: str, exc: ApiError) -> str:
    why = (
        "is not enabled for this account"
        if exc.feature_gated
        else "does not exist on this DataRobot version"
    )
    return (
        f"{primary} {why}; used legacy /verifySQL/ (max {LEGACY_MAX_ROWS} rows, "
        "no types)"
    )


def run_verify_sql(
    client: DataRobotClient,
    datastore_id: str,
    sql: str,
    max_rows: int,
    credential: str | None,
    notes: list[str],
) -> Result:
    credential_id = require_credential(client, datastore_id, credential)
    capped = min(max_rows, LEGACY_MAX_ROWS)
    if capped < max_rows:
        notes.append(f"maxRows capped at {LEGACY_MAX_ROWS} on the legacy route")
    data = client.call(
        "POST",
        f"externalDataStores/{datastore_id}/verifySQL/",
        body={"query": sql, "maxRows": capped, "credentialId": credential_id},
        timeout=SQL_TIMEOUT,
        retries=1,
    )
    return preview_result(data, "verifySQL (legacy)", capped, notes)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_datastores(client: DataRobotClient, args: argparse.Namespace) -> int:
    params = {"type": "all"}
    if args.name:
        params["name"] = args.name
    data = _as_dict(client.call("GET", "externalDataStores/", params=params))
    rows = [
        [
            store.get("id"),
            store.get("canonicalName"),
            store.get("type"),
            store.get("driverClassType"),
            store.get("role"),
            sql_support(store),
        ]
        for store in map(_as_dict, _as_list(data.get("data")))
    ]
    columns = ["id", "name", "type", "driver", "role", "sql"]
    notes = [
        "role = your access to the connection (OWNER, EDITOR, CONSUMER)",
        (
            "sql = what DataRobot can do with the connection's driver; writes need "
            "'read (fast) + write'. It does not check the credential's grants"
        ),
    ]
    if not args.name:
        notes.append(f"these are all {len(rows)} connections you can access")
    return emit(Result(columns, rows, notes=notes), args)


def cmd_credentials(client: DataRobotClient, args: argparse.Namespace) -> int:
    rows = [
        [
            item.get("credentialId"),
            item.get("name"),
            item.get("credentialType"),
            "yes" if item.get("isDefault") else "",
        ]
        for item in credential_associations(client, args.datastore_id)
    ]
    return emit(Result(["credentialId", "name", "type", "default"], rows), args)


def cmd_schemas(client: DataRobotClient, args: argparse.Namespace) -> int:
    credential_id = require_credential(client, args.datastore_id, args.credential_id)
    data = _as_dict(
        client.call(
            "POST",
            f"externalDataStores/{args.datastore_id}/schemas/",
            body={"credentialId": credential_id},
        )
    )
    catalog = data.get("catalog")
    catalogs = dict.fromkeys(str(c) for c in _as_list(data.get("catalogs")))
    rows = [["catalog", c, "yes" if c == catalog else ""] for c in catalogs]
    rows += [["schema", s, ""] for s in _as_list(data.get("schemas"))]
    return emit(Result(["kind", "name", "current"], rows), args)


def cmd_tables(client: DataRobotClient, args: argparse.Namespace) -> int:
    credential_id = require_credential(client, args.datastore_id, args.credential_id)
    body: dict[str, Any] = {"credentialId": credential_id}
    if args.schema:
        body["schema"] = args.schema
    if args.catalog:
        body["catalog"] = args.catalog
    data = _as_dict(
        client.call(
            "POST", f"externalDataStores/{args.datastore_id}/tables/", body=body
        )
    )
    tables = [_as_dict(t) for t in _as_list(data.get("tables"))]
    needle = (args.like or "").lower()
    rows = [
        [t.get("catalog"), t.get("schema"), t.get("name"), t.get("type")]
        for t in tables
        if needle in str(t.get("name") or "").lower()
    ]
    notes = []
    if needle:
        notes.append(f"{len(rows)} of {len(tables)} names contain {args.like!r}")
    if not tables:
        notes.append(
            "no rows: discovery lists only objects the credential can access; check the schema name and its case, and the credential's grants"
        )
    return emit(Result(["catalog", "schema", "name", "type"], rows, notes=notes), args)


def cmd_columns(client: DataRobotClient, args: argparse.Namespace) -> int:
    credential_id = require_credential(client, args.datastore_id, args.credential_id)
    body: dict[str, Any] = {"credentialId": credential_id, "table": args.table}
    if args.schema:
        body["schema"] = args.schema
    if args.catalog:
        body["catalog"] = args.catalog
    data = _as_dict(
        client.call(
            "POST", f"externalDataStores/{args.datastore_id}/columns/", body=body
        )
    )
    rows = [
        [c.get("name"), c.get("dataType"), c.get("precision"), c.get("scale")]
        for c in map(_as_dict, _as_list(data.get("columns")))
    ]
    notes = (
        []
        if rows
        else [
            "no rows: discovery lists only objects the credential can access; check the schema name and its case, and the credential's grants"
        ]
    )
    columns = ["name", "dataType", "precision", "scale"]
    return emit(Result(columns, rows, notes=notes), args)


def cmd_preview(client: DataRobotClient, args: argparse.Namespace) -> int:
    max_rows = args.max_rows
    notes: list[str] = []
    if args.route != "legacy":
        body: dict[str, Any] = {"table": args.table, "maxRows": max_rows}
        for key in ("schema", "catalog"):
            if getattr(args, key):
                body[key] = getattr(args, key)
        if args.credential_id:
            body["credentialId"] = args.credential_id
        try:
            data = client.call(
                "POST",
                f"externalDataStores/{args.datastore_id}/preview/",
                body=body,
                timeout=SQL_TIMEOUT,
                retries=1,
            )
            result = preview_result(data, "preview", max_rows, notes)
            result.sample = True
            return emit(result, args)
        except ApiError as exc:
            if args.route == "new" or not (exc.feature_gated or exc.route_missing):
                raise
            notes.append(_fallback_note("/preview/", exc))
    driver = str(get_store(client, args.datastore_id).get("driverClassType") or "")
    parts = (args.catalog, args.schema, args.table)
    name = ".".join(quote_identifier(p, driver) for p in parts if p)
    # Every part is quoted by quote_identifier and the result must pass check_read_only.
    sql = check_read_only(f"SELECT * FROM {name}")  # noqa: S608
    result = run_verify_sql(
        client, args.datastore_id, sql, max_rows, args.credential_id, notes
    )
    result.sample = True
    return emit(result, args)


def cmd_query(client: DataRobotClient, args: argparse.Namespace) -> int:
    raw = read_sql(args)
    sql = check_read_only(raw)
    binds = parse_binds(args.bind)
    max_rows = args.max_rows
    notes: list[str] = []
    store: dict[str, Any] | None = None
    if end_depends_on_dialect(raw):
        # e.g. '# note' is a comment in MySQL but an operator in PostgreSQL.
        store = get_store(client, args.datastore_id)
        sql = strip_trailing(raw, lexings_for(str(store.get("driverClassType") or "")))
    if binds is not None:
        if args.route == "legacy":
            raise UsageError(
                "The legacy /verifySQL/ route has no bind parameters; inline the "
                "values as SQL literals."
            )
        # The legacy engine behind non-native drivers silently drops bind values.
        store = store or get_store(client, args.datastore_id)
        if not sql_support(store).startswith("read (fast)"):
            raise UsageError(
                f"Bind parameters are ignored for {store.get('driverClassType')} "
                "connections (legacy path). Inline the values as SQL literals."
            )
    if args.route != "legacy":
        body: dict[str, Any] = {"sql": sql, "maxRows": max_rows}
        if args.credential_id:
            body["credentialId"] = args.credential_id
        if binds is not None:
            body["bindParams"] = binds
        try:
            data = client.call(
                "POST",
                f"externalDataStores/{args.datastore_id}/previewQuery/",
                body=body,
                timeout=SQL_TIMEOUT,
                retries=1,
            )
            return emit(preview_result(data, "previewQuery", max_rows, notes), args)
        except ApiError as exc:
            if args.route == "new" or not (exc.feature_gated or exc.route_missing):
                raise
            notes.append(_fallback_note("/previewQuery/", exc))
    if binds is not None:
        raise RouteUnavailable(
            "/previewQuery/ is not available here and the legacy /verifySQL/ route "
            "has no bind parameters. Inline the values as SQL literals, or ask a "
            "DataRobot admin to enable the Future Public API for your account."
        )
    result = run_verify_sql(
        client, args.datastore_id, sql, max_rows, args.credential_id, notes
    )
    return emit(result, args)


@dataclass
class WritePlan:
    sql: str
    binds: list[Any] | None
    count: int
    warnings: list[str]
    store: dict[str, Any]
    credential_id: str | None
    credential_label: str
    token: str

    @property
    def writable(self) -> bool:
        return sql_support(self.store) == "read (fast) + write"


def build_plan(client: DataRobotClient, args: argparse.Namespace) -> WritePlan:
    """Gather what an approval needs. Reads connection metadata only."""
    sql = read_sql(args).strip()
    binds = parse_binds(args.bind)
    count, warnings = analyze_write(sql)
    if not count:
        raise UsageError("SQL is empty.")
    store = get_store(client, args.datastore_id)
    credential_id, label = resolve_credential(
        client, args.datastore_id, args.credential_id
    )
    if not credential_id:
        warnings.append(
            "No credential: pass --credential-id (see `credentials`); the write "
            "would fail with 422."
        )
    token = plan_token(args.datastore_id, credential_id or "", sql, json.dumps(binds))
    return WritePlan(sql, binds, count, warnings, store, credential_id, label, token)


PLAN_CHECKS = (
    "Before asking: the script does not inspect the target. Confirm it exists and "
    "is a table, not a view (`tables`, `columns`), and measure the impact with a read."
)


def print_plan(plan: WritePlan, stale_token: bool = False) -> int:
    store = plan.store
    driver = str(store.get("driverClassType") or "?")
    name = f"'{store.get('canonicalName')}' ({store.get('id')})"
    if not plan.writable:
        print(
            f"CANNOT WRITE THROUGH DATAROBOT: {name} uses driver {driver}. "
            "DataRobot runs writes only for Snowflake, BigQuery, Databricks, SAP "
            "Datasphere, and Trino connections. Nothing to approve; use the "
            "datarobot-connectivity-jdbc-sql skill with the database's own JDBC "
            "URL and credentials instead."
        )
        return EXIT_UNAVAILABLE
    print(
        "WRITE PLAN (nothing has run). Show it to the user and get explicit approval."
    )
    print(PLAN_CHECKS)
    print(
        f"  connection : {name}, type {store.get('type')}, driver {driver}, "
        f"your role {store.get('role')}"
    )
    print(f"  credential : {plan.credential_label}")
    print(f"  statements : {plan.count}, sent verbatim in one request")
    print(f"  atomicity  : {TRANSACTION_NOTES.get(driver, DEFAULT_TRANSACTION_NOTE)}")
    print("  sql:")
    for line in plan.sql.splitlines():
        print(f"    {line}")
    if plan.binds is not None:
        print(f"  binds      : {json.dumps(plan.binds)}")
    for warning in plan.warnings:
        print(f"  WARNING: {warning}")
    if stale_token:
        print(
            "  NOTE: the --confirm token does not match this plan: the SQL, binds, "
            "credential, or connection changed. Get approval again."
        )
    print(
        "After the user approves this exact plan, run `execute` with the same "
        f"arguments plus --confirm {plan.token}"
    )
    return EXIT_CONFIRM if stale_token else EXIT_OK


def cmd_plan(client: DataRobotClient, args: argparse.Namespace) -> int:
    return print_plan(build_plan(client, args))


ROUTE_PROBES = (
    ("previewQuery", "read SQL (query)"),
    ("preview", "table preview (preview)"),
    ("executeUpdate", "DML/DDL (execute)"),
)


def cmd_routes(client: DataRobotClient, args: argparse.Namespace) -> int:
    """Probe each route with an empty body; validation rejects it before any SQL."""
    store = get_store(client, args.datastore_id)
    support = sql_support(store)
    driver = store.get("driverClassType") or "?"
    rows = []
    for route, purpose in ROUTE_PROBES:
        try:
            client.call(
                "POST", f"externalDataStores/{args.datastore_id}/{route}/", body={}
            )
            status = "available"
        except ApiError as exc:
            if exc.status == 422:
                status = "available"
            elif exc.feature_gated:
                status = (
                    "not in your seat license"
                    if "seat license" in exc.message
                    else "not enabled for this account"
                )
            elif exc.route_missing:
                status = "missing on this DataRobot version"
            else:
                status = f"HTTP {exc.status}: {exc.message[:80]}"
        if (
            status == "available"
            and route == "executeUpdate"
            and "write" not in support
        ):
            status = f"available to your account, but driver {driver} cannot write"
        rows.append([route, purpose, status])
    notes = [
        f"connection {store.get('canonicalName')!r}: driver {driver}, sql = {support}",
        "probed with empty requests that fail validation; no SQL ran",
        (
            "reads fall back to the legacy /verifySQL/ when the newer routes are "
            "unavailable; writes have no fallback"
        ),
    ]
    return emit(Result(["route", "used by", "status"], rows, notes=notes), args)


def cmd_execute(client: DataRobotClient, args: argparse.Namespace) -> int:
    plan = build_plan(client, args)
    if not plan.writable:
        return print_plan(plan)
    if args.confirm != plan.token:
        return print_plan(plan, stale_token=True)
    sql, binds, count = plan.sql, plan.binds, plan.count
    body: dict[str, Any] = {"sql": sql}
    if args.credential_id:
        body["credentialId"] = args.credential_id
    if binds is not None:
        body["bindParams"] = binds
    unknown = (
        "The write may or may not have run. Check with a `query` before retrying; "
        "never re-run blindly."
    )
    try:
        data = client.call(
            "POST",
            f"externalDataStores/{args.datastore_id}/executeUpdate/",
            body=body,
            timeout=SQL_TIMEOUT,
            retries=0,
        )
    except ApiError as exc:
        if exc.feature_gated:
            raise RouteUnavailable(
                "Writes through data connections are not enabled for this account "
                f"({exc.message}). Ask a DataRobot admin, or use the "
                "datarobot-connectivity-jdbc-sql skill with your own JDBC URL."
            ) from None
        if exc.route_missing:
            raise RouteUnavailable(
                "This DataRobot version has no /executeUpdate/ route (needs 11.10+)."
            ) from None
        if exc.status == 409:
            raise RouteUnavailable(
                f"{exc.message} See `datastores`, column sql."
            ) from None
        if exc.status == 408 or exc.status >= 500:
            print(f"error: HTTP {exc.status}: {exc.message}", file=sys.stderr)
            print(f"error: {unknown}", file=sys.stderr)
            return EXIT_API
        raise
    except TransportError as exc:
        print(f"error: no usable response ({exc}). {unknown}", file=sys.stderr)
        return EXIT_API
    message = str(_as_dict(data).get("message", ""))
    if message == "OK":
        print(
            f"OK: {count} statement(s) executed. No row count is returned; verify "
            "the change with `query`."
        )
        return EXIT_OK
    print(f"FAILED: the database reported: {message}")
    return EXIT_WRITE_FAILED


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

DISCOVERY_HINT = (
    "The schema or table was not found, or this credential cannot see it. List "
    "what exists with `schemas` and `tables --schema S`, and check the name's case."
)

HINTS: list[tuple[Callable[[ApiError], bool], str]] = [
    (
        lambda e: e.status == 401,
        (
            "The API token was rejected: check DATAROBOT_API_TOKEN or run the "
            "datarobot-setup skill."
        ),
    ),
    (
        lambda e: 300 <= e.status < 400,
        (
            "DataRobot answered with a redirect, which the script does not follow "
            "because it would carry the API token elsewhere. Check DATAROBOT_ENDPOINT "
            "(https, host, /api/v2)."
        ),
    ),
    (
        lambda e: "default credentials were not found" in e.message,
        (
            "Pass --credential-id (see `credentials`) or set a default credential. This "
            "check runs before the connection lookup, so also confirm the id with "
            "`datastores`."
        ),
    ),
    (
        lambda e: "credential does not exist" in e.message,
        "Wrong or unshared credential id; list valid ones with `credentials`.",
    ),
    (
        lambda e: e.status == 403 and "required permissions" in e.message,
        "The database rejected the credential (wrong password or missing privilege).",
    ),
    (lambda e: e.status == 404, "Check the data connection id with `datastores`."),
    (
        lambda e: e.status == 409,
        (
            "This connection type does not support the operation; see `datastores`, "
            "column sql."
        ),
    ),
    (
        lambda e: e.status == 408,
        (
            "No answer within the 300 s server limit. Common causes: a stopped or "
            "cold warehouse (Databricks, Snowflake) still starting, or a heavy query. "
            "Retry the read once the warehouse is up; add filters, LIMIT, or "
            "aggregation."
        ),
    ),
    (lambda e: e.status == 429, "Rate limited; wait and retry the read."),
    (
        lambda e: "invalid_grant" in e.message or "oauth" in e.message.lower(),
        (
            "The stored OAuth credential expired or was revoked. Re-authorize it in "
            "DataRobot, or pick another credential (`credentials`)."
        ),
    ),
    (
        lambda e: e.status == 400,
        (
            "The database rejected the SQL: check that the objects exist (`tables`, "
            "`columns`), identifier case and quoting, and the dialect "
            "(references/connector-support.md)."
        ),
    ),
]


class _Parser(argparse.ArgumentParser):
    """Usage errors exit with EXIT_USAGE, distinct from API errors."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _int_in(low: int, high: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return value

    return parse


def _object_id(text: str) -> str:
    if not OBJECT_ID.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a DataRobot id (24 hex characters)"
        )
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    output = _Parser(add_help=False)
    output.add_argument("--format", choices=("table", "csv", "json"), default="table")
    output.add_argument("--out", help="write all rows to FILE (.csv or .json)")
    output.add_argument(
        "--show",
        type=_int_in(0, 1_000_000),
        default=None,
        help="rows printed (default 100 for listings, 20 for preview and query)",
    )
    output.add_argument(
        "--width", type=_int_in(4, 10_000), default=40, help="max table cell width"
    )

    conn = _Parser(add_help=False)
    conn.add_argument(
        "--datastore-id", required=True, type=_object_id, help="data connection id"
    )
    conn.add_argument(
        "--credential-id",
        type=_object_id,
        help="stored credential id (default: the connection's default)",
    )

    sql = _Parser(add_help=False)
    group = sql.add_mutually_exclusive_group(required=True)
    group.add_argument("--sql", help="SQL text")
    group.add_argument("--sql-file", help="file with the SQL ('-' reads stdin)")
    sql.add_argument("--bind", help="JSON list of values for ? placeholders")

    table = _Parser(add_help=False)
    table.add_argument("--schema")
    table.add_argument("--catalog")

    route = _Parser(add_help=False)
    route.add_argument(
        "--route",
        choices=("auto", "new", "legacy"),
        default="auto",
        help="auto: new route, legacy /verifySQL/ if unavailable (default)",
    )

    p = sub.add_parser("datastores", parents=[output], help="list data connections")
    p.add_argument("--name", help="filter by name (case-insensitive contains)")
    p.set_defaults(handler=cmd_datastores, width=80)

    p = sub.add_parser("credentials", parents=[output], help="list stored credentials")
    p.add_argument("--datastore-id", required=True, type=_object_id)
    p.set_defaults(handler=cmd_credentials, width=80)

    p = sub.add_parser(
        "schemas", parents=[conn, output], help="list catalogs and schemas"
    )
    p.set_defaults(handler=cmd_schemas)

    p = sub.add_parser("tables", parents=[conn, table, output], help="list tables")
    p.add_argument("--like", help="keep tables whose name contains this text")
    p.set_defaults(handler=cmd_tables)

    p = sub.add_parser("columns", parents=[conn, table, output], help="list columns")
    p.add_argument("--table", required=True)
    p.set_defaults(handler=cmd_columns)

    p = sub.add_parser(
        "preview", parents=[conn, table, route, output], help="preview table rows"
    )
    p.add_argument("--table", required=True)
    p.add_argument("--max-rows", type=_int_in(1, MAX_ROWS), default=20)
    p.set_defaults(handler=cmd_preview)

    p = sub.add_parser(
        "query", parents=[conn, sql, route, output], help="run one read-only query"
    )
    p.add_argument("--max-rows", type=_int_in(1, MAX_ROWS), default=100)
    p.set_defaults(handler=cmd_query)

    p = sub.add_parser(
        "routes", parents=[output], help="check which newer routes you can use"
    )
    p.add_argument("--datastore-id", required=True, type=_object_id)
    p.set_defaults(handler=cmd_routes, width=80)

    p = sub.add_parser(
        "plan", parents=[conn, sql], help="show the write plan and its confirm token"
    )
    p.set_defaults(handler=cmd_plan)

    p = sub.add_parser(
        "execute", parents=[conn, sql], help="run DML/DDL approved via `plan`"
    )
    p.add_argument(
        "--confirm",
        metavar="TOKEN",
        required=True,
        help="token printed by `plan` for the approved SQL",
    )
    p.set_defaults(handler=cmd_execute)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if getattr(args, "show", 0) is None:
        args.show = 20 if args.handler in (cmd_preview, cmd_query) else 100
    try:
        out = getattr(args, "out", None)
        if out and not Path(out).resolve().parent.is_dir():
            raise UsageError(f"--out directory does not exist: {Path(out).parent}")
        client = DataRobotClient(*load_config())
        return int(args.handler(client, args))
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except RouteUnavailable as exc:
        print(f"unavailable: {exc}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    except ApiError as exc:
        print(f"error: HTTP {exc.status}: {exc.message}", file=sys.stderr)
        if exc.status == 400 and args.handler in (cmd_tables, cmd_columns):
            print(f"hint: {DISCOVERY_HINT}", file=sys.stderr)
            return EXIT_API
        for matches, hint in HINTS:
            if matches(exc):
                print(f"hint: {hint}", file=sys.stderr)
                break
        return EXIT_API
    except TransportError as exc:
        print(f"error: could not reach DataRobot: {exc}", file=sys.stderr)
        return EXIT_API
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
