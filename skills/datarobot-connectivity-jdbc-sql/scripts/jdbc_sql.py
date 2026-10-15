#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run SQL against a database through DataRobot with a JDBC URL you supply.

Commands (run ``python jdbc_sql.py <command> -h`` for options):

  check     Connect and run a trivial query (SELECT 1)
  tables    List tables and views (dialect-aware catalog SQL)
  columns   List the columns of a table
  query     Run one read-only SQL query          -> POST /jdbcDataPreview/
  plan      Show the plan and confirm token for DML/DDL (makes no API call)
  execute   Run DML/DDL; needs the --confirm token from `plan`
                                                 -> POST /jdbcExecution/
  routes    Check which JDBC routes this DataRobot and API token can use
            (requests that fail validation; no SQL runs)

Connection: --jdbc-url, or an env var (--jdbc-url-env; default JDBC_URL, then
JDBC_URI). Driver properties: --param key=value, --param-env key=ENV_VAR (use
this for secrets), and a JSON object from --params-json-env (default
JDBC_CONNECTION_PARAMETERS, read only with the URL from JDBC_URL/JDBC_URI).
--env-file loads KEY=VALUE lines first, including DataRobot auth.

Auth: DATAROBOT_ENDPOINT (ends in /api/v2) and DATAROBOT_API_TOKEN together, or
both keys in drconfig.yaml (DATAROBOT_CONFIG_FILE, else
$XDG_CONFIG_HOME/datarobot/drconfig.yaml, else ~/.config/datarobot/drconfig.yaml).
Standard library only; Python 3.9+.

Exit codes: 0 ok, 1 usage or config error, 2 API error or unknown write
outcome, 3 --confirm token does not match the current plan, 4 the database
reported a write failure, 5 route unavailable.
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
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import IO, Any, Callable, NoReturn, Sequence

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_API = 2
EXIT_CONFIRM = 3
EXIT_WRITE_FAILED = 4
EXIT_UNAVAILABLE = 5

PREVIEW_TIMEOUT = 330  # server deadline for previews is 300 s
EXECUTE_TIMEOUT = 90  # server deadline for executes is 30 s
MAX_ROWS = 10_000
MAX_BIND_PARAMS = 100
USER_AGENT = "datarobot-agent-skills/datarobot-connectivity-jdbc-sql"
PREVIEW_ROUTE = "jdbcDataPreview/"
EXECUTE_ROUTE = "jdbcExecution/"
PROBE_TIMEOUT = 30  # validation answers at once; no database is contacted

# `query` accepts only statements that start with one of these...
READ_STARTS = frozenset("SELECT WITH VALUES TABLE".split())
# ...and contain none of these words anywhere outside quotes and comments.
WRITE_WORDS = frozenset("INSERT UPDATE DELETE MERGE UPSERT INTO".split())
DML_WORDS = frozenset("INSERT UPDATE DELETE MERGE UPSERT".split())
# Reads that cannot run inside the `select * from (<sql>) _table` wrapper.
NOT_WRAPPABLE = frozenset("SHOW DESCRIBE DESC EXPLAIN".split())
SENSITIVE_KEY = re.compile(
    r"(pass|pwd|secret|token|private_?key|pvtkey|credential|apikey|api_key"
    r"|clientkey|accountkey)",
    re.I,
)
# Dialects whose string literals escape with a backslash.
BACKSLASH_DIALECTS = frozenset({"bigquery", "databricks", "spark"})
BACKTICK_DIALECTS = frozenset({"mysql", "mariadb", "bigquery", "databricks", "spark"})
CATALOG_DIALECTS = frozenset(
    {"snowflake", "databricks", "spark", "trino", "sqlserver", "bigquery"}
)


class UsageError(Exception):
    """Bad arguments or configuration."""


class RouteUnavailable(Exception):
    """The route is not available on this DataRobot installation."""


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
    def route_missing(self) -> bool:
        """A JSON 404 for the route itself (older DataRobot)."""
        return (
            self.status == 404
            and self.from_body
            and self.message.strip() == "Not Found"
        )


# --------------------------------------------------------------------------- #
# Secrets: every known secret value is scrubbed from printed messages.
# --------------------------------------------------------------------------- #

_SECRETS: set[str] = set()


def remember_secret(value: str) -> None:
    if len(value) >= 3:
        _SECRETS.add(value)


def scrub(text: str) -> str:
    for secret in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


def _userinfo_password(url: str) -> tuple[int, int] | None:
    """Span of the password in `//user:password@host`, using the last `@`."""
    start = url.find("//")
    if start == -1:
        return None
    start += 2
    end = len(url)
    for separator in "?;":
        position = url.find(separator, start)
        if position != -1:
            end = min(end, position)
    at = url.rfind("@", start, end)
    colon = url.find(":", start, at) if at != -1 else -1
    return (colon + 1, at) if colon != -1 else None


_URL_PROPERTY = re.compile(
    r"([?&;(,]\s*)([A-Za-z0-9_.\-]+)(\s*=\s*)(\{(?:[^}]|\}\})*\}|[^&;),]*)"
)


def mask_url(url: str) -> str:
    """Hide credentials in a JDBC URL (user:pass@, ?password=, ;PWD={...})."""
    span = _userinfo_password(url)
    if span:
        url = url[: span[0]] + "***" + url[span[1] :]
    return _URL_PROPERTY.sub(
        lambda m: (
            m.group(1)
            + m.group(2)
            + m.group(3)
            + ("***" if SENSITIVE_KEY.search(m.group(2)) else m.group(4))
        ),
        url,
    )


def _remember_url_secrets(url: str) -> None:
    span = _userinfo_password(url)
    if span:
        remember_secret(url[span[0] : span[1]])
    for match in _URL_PROPERTY.finditer(url):
        if SENSITIVE_KEY.search(match.group(2)):
            value = match.group(4)
            remember_secret(value)
            if value.startswith("{") and value.endswith("}"):
                remember_secret(value[1:-1])


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


def load_env_file(path: str) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing values."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise UsageError(f"cannot read --env-file: {exc}") from None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(
            r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped
        )
        if not match:
            continue
        key, raw = match.groups()
        if raw[:1] in ("'", '"'):
            close = raw.find(raw[0], 1)
            value = raw[1:close] if close != -1 else raw[1:]
        else:
            value = re.sub(r"\s+#.*$", "", raw).strip()
        os.environ.setdefault(key, value)


def _ssl_context() -> ssl.SSLContext | None:
    verify = os.environ.get("DATAROBOT_SSL_VERIFY", "").strip()
    if verify.lower() in ("false", "0", "no", "off"):
        return ssl._create_unverified_context()
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

    def post(
        self, route: str, body: dict[str, Any], *, timeout: float, retries: int = 0
    ) -> Any:
        data = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        for attempt in range(retries + 1):
            request = urllib.request.Request(
                f"{self.endpoint}/{route}", data=data, headers=headers, method="POST"
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
            except (urllib.error.URLError, socket.timeout, OSError) as exc:
                reason = getattr(exc, "reason", None) or exc
                raise TransportError(str(reason)) from None
        raise TransportError("request was not sent")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


# --------------------------------------------------------------------------- #
# Connection: URL and driver properties
# --------------------------------------------------------------------------- #


@dataclass
class Connection:
    url: str
    parameters: dict[str, str]
    sources: dict[str, str] = field(default_factory=dict)  # property -> origin

    @property
    def dialect(self) -> str:
        match = re.match(r"jdbc:([a-z0-9]+):", self.url, re.I)
        return match.group(1).lower() if match else ""

    def masked_parameters(self) -> dict[str, str]:
        """Secrets show where they come from, never their value."""
        masked = dict(self.parameters)
        for key in masked:
            if SENSITIVE_KEY.search(key):
                source = self.sources.get(key)
                masked[key] = f"*** ({source})" if source else "***"
        return masked


def _as_property(value: Any) -> str:
    """Driver properties travel as strings; JSON booleans become true/false."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        raise UsageError("driver property values must be strings, numbers, or booleans")
    return str(value)


def build_connection(args: argparse.Namespace) -> Connection:
    if args.jdbc_url is not None:
        url = args.jdbc_url.strip()
        if not url:
            raise UsageError("--jdbc-url is empty.")
    else:
        if args.jdbc_url_env is not None and not args.jdbc_url_env.strip():
            raise UsageError("--jdbc-url-env is empty.")
        names = [args.jdbc_url_env] if args.jdbc_url_env else ["JDBC_URL", "JDBC_URI"]
        url = next((os.environ[n] for n in names if os.environ.get(n)), "").strip()
        if not url:
            raise UsageError(
                f"No JDBC URL: pass --jdbc-url or set {' or '.join(names)} "
                "(e.g. in .env, loaded with --env-file .env)."
            )
    _remember_url_secrets(url)
    if args.jdbc_url is not None and mask_url(url) != url:
        print(
            "warning: the JDBC URL on the command line contains a secret; prefer "
            "--jdbc-url-env and --param-env.",
            file=sys.stderr,
        )
    if not url.lower().startswith("jdbc:"):
        raise UsageError("The JDBC URL must start with 'jdbc:'.")
    parameters: dict[str, str] = {}
    sources: dict[str, str] = {}
    default_url = args.jdbc_url is None and not args.jdbc_url_env
    json_env = args.params_json_env or "JDBC_CONNECTION_PARAMETERS"
    if not args.params_json_env and not default_url:
        if os.environ.get(json_env, "").strip():
            print(
                f"note: {json_env} is ignored because the URL was given explicitly; "
                f"pass --params-json-env {json_env} to use it with this URL.",
                file=sys.stderr,
            )
        json_env = ""
    raw_json = os.environ.get(json_env, "").strip() if json_env else ""
    if raw_json:
        try:
            loaded = json.loads(raw_json)
        except ValueError:
            raise UsageError(f"{json_env} is not valid JSON.") from None
        if not isinstance(loaded, dict):
            raise UsageError(f"{json_env} must hold a JSON object.")
        parameters.update(
            {str(k): _as_property(v) for k, v in loaded.items() if v is not None}
        )
        sources.update({key: f"env {json_env}" for key in parameters})
    elif args.params_json_env:
        raise UsageError(f"{json_env} is not set.")
    for item in args.param or []:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise UsageError("--param needs KEY=VALUE (an argument had no '=').")
        if SENSITIVE_KEY.search(key):
            print(
                f"warning: --param {key}=... puts a secret on the command line; "
                f"prefer --param-env {key}=ENV_VAR.",
                file=sys.stderr,
            )
        parameters[key] = value
        sources[key] = "command line"
    for item in args.param_env or []:
        key, sep, env_name = item.partition("=")
        if not sep or not key or not env_name:
            raise UsageError("--param-env needs KEY=ENV_VAR.")
        if env_name not in os.environ:
            raise UsageError(
                f"--param-env {key}: environment variable {env_name} is not set."
            )
        parameters[key] = os.environ[env_name]
        sources[key] = f"env {env_name}"
    for key, value in parameters.items():
        if SENSITIVE_KEY.search(key):
            remember_secret(value)
    return Connection(url, parameters, sources)


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


def lexings_for(dialect: str) -> tuple[Lexing, ...]:
    """How the URL's database lexes SQL; BigQuery takes '#' and any '--'."""
    if dialect in ("mysql", "mariadb"):
        return (
            Lexing(backslash_escapes=True, mysql_comments=True, dollar_quotes=False),
        )
    if dialect == "bigquery":
        return (
            Lexing(backslash_escapes=True, mysql_comments=True, dollar_quotes=False),
            Lexing(backslash_escapes=True, dollar_quotes=False),
        )
    if dialect in ("databricks", "spark"):
        return (
            Lexing(backslash_escapes=True, nested_comments=True, dollar_quotes=False),
        )
    if dialect == "postgresql":
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

    DataRobot appends the row limit on the same line, so a trailing comment the
    database recognizes would swallow it.
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


def plan_token(*parts: str) -> str:
    """Short fingerprint of an approved write; --confirm must repeat it."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:10]


def check_read_only(sql: str, lexings: Sequence[Lexing] = (STANDARD,)) -> str:
    """Return SQL ready for the preview route, or raise UsageError.

    A keyword check cannot see side effects of functions; only a read-only
    database login guarantees a read.
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
        if keyword in NOT_WRAPPABLE:
            raise UsageError(
                f"{keyword} cannot run here: DataRobot wraps the query in a "
                "subquery with a row limit. Use `tables`, `columns`, or "
                "information_schema queries instead."
            )
        if keyword not in READ_STARTS:
            raise UsageError(
                f"`query` only runs reads (SELECT, WITH, VALUES, TABLE); this SQL "
                f"starts with {keyword or 'no keyword'}. Use `execute`, which "
                "needs the user's explicit approval."
            )
        found = WRITE_WORDS & set(words)
        if found:
            raise UsageError(
                f"`query` is read-only and this SQL contains {sorted(found)[0]}. "
                "Use `execute`, which needs the user's explicit approval."
            )
    return strip_trailing(sql, lexings)


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
        elif keyword in READ_STARTS | NOT_WRAPPABLE and not DML_WORDS & found:
            warnings.append(
                "A statement only reads data; `execute` returns no rows. Use "
                "`query` (SELECT) or the `tables`/`columns` commands instead."
            )
    if len(statements) > 1:
        warnings.append(
            f"{len(statements)} statements in one call: not atomic, and most "
            "drivers reject it unless enabled (MySQL allowMultiQueries=true, "
            "Snowflake MULTI_STATEMENT_COUNT=0). Prefer one statement per call."
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
    if any(isinstance(item, (dict, list)) or item == "" for item in value):
        raise UsageError(
            "--bind values must be non-empty strings, numbers, booleans, or null."
        )
    return value or None


# --------------------------------------------------------------------------- #
# Dialect-aware catalog SQL (there are no metadata routes for JDBC URLs)
# --------------------------------------------------------------------------- #


def _literal(value: str, dialect: str) -> str:
    if dialect in BACKSLASH_DIALECTS:
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if dialect in ("mysql", "mariadb"):
        return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"
    return "'" + value.replace("'", "''") + "'"


def _identifier(name: str, dialect: str) -> str:
    if dialect in BACKTICK_DIALECTS:
        if "`" in name:
            raise UsageError("Names containing a backtick are not supported.")
        return f"`{name}`"
    if dialect == "sqlserver":
        return "[" + name.replace("]", "]]") + "]"
    return '"' + name.replace('"', '""') + '"'


def check_sql(dialect: str) -> str:
    return "SELECT 1 AS ok FROM DUMMY" if dialect == "sap" else "SELECT 1 AS ok"


def _catalog_prefix(dialect: str, catalog: str | None, schema: str | None) -> str:
    if dialect == "bigquery":
        if not schema:
            raise UsageError("BigQuery needs --schema <dataset>.")
        parts = [p for p in (catalog, schema) if p]
        return ".".join(_identifier(p, dialect) for p in parts) + ".INFORMATION_SCHEMA."
    if not catalog:
        return (
            "INFORMATION_SCHEMA." if dialect == "sqlserver" else "information_schema."
        )
    if dialect not in CATALOG_DIALECTS:
        raise UsageError(
            f"--catalog is not supported for {dialect or 'this driver'}; put the "
            "database in the JDBC URL instead."
        )
    view = "INFORMATION_SCHEMA." if dialect == "sqlserver" else "information_schema."
    return _identifier(catalog, dialect) + "." + view


def _name_filter(column: str, like: str | None, dialect: str) -> str:
    """Server-side prefilter for --like. Characters that LIKE could treat as
    escapes or classes become `_`, so the match is never narrower than the exact
    client-side filter that follows."""
    if not like:
        return ""
    pattern = "%" + re.sub(r"[\\\[\]]", "_", like.lower()) + "%"
    return f"LOWER({column}) LIKE {_literal(pattern, dialect)}"


def tables_sql(
    dialect: str, catalog: str | None, schema: str | None, like: str | None = None
) -> str:
    if dialect == "postgresql" and not catalog:
        # pg_catalog lists objects the login cannot read, unlike information_schema.
        conditions = [
            "c.relkind IN ('r', 'p', 'v', 'm', 'f')",
            "LEFT(n.nspname, 3) <> 'pg_'",
            "n.nspname <> 'information_schema'",
        ]
        if schema:
            conditions.append(f"UPPER(n.nspname) = UPPER({_literal(schema, dialect)})")
        if like:
            conditions.append(_name_filter("c.relname", like, dialect))
        return (
            "SELECT n.nspname AS table_schema, c.relname AS table_name, "
            "CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' "
            "WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END AS table_type, "
            "has_schema_privilege(n.oid, 'USAGE') "
            "AND has_table_privilege(c.oid, 'SELECT') AS readable "
            "FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE {' AND '.join(conditions)}"
        )
    if dialect == "sap":
        where = (
            f"UPPER(SCHEMA_NAME) = UPPER({_literal(schema, dialect)})"
            if schema
            else "LEFT(SCHEMA_NAME, 4) <> '_SYS' AND SCHEMA_NAME <> 'SYS'"
        )
        tables_where = views_where = where
        if like:
            tables_where += " AND " + _name_filter("TABLE_NAME", like, dialect)
            views_where += " AND " + _name_filter("VIEW_NAME", like, dialect)
        return (
            "SELECT SCHEMA_NAME AS table_schema, TABLE_NAME AS table_name, "
            f"'TABLE' AS table_type FROM SYS.TABLES WHERE {tables_where} UNION ALL "
            f"SELECT SCHEMA_NAME, VIEW_NAME, 'VIEW' FROM SYS.VIEWS WHERE {views_where}"
        )
    source = _catalog_prefix(dialect, catalog, schema)
    if dialect == "sqlserver":
        columns, schema_column = "TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE", "TABLE_SCHEMA"
    else:
        columns, schema_column = "table_schema, table_name, table_type", "table_schema"
    name_column = "TABLE_NAME" if dialect == "sqlserver" else "table_name"
    if dialect == "bigquery":
        where = ""
    elif schema:
        where = f" WHERE UPPER({schema_column}) = UPPER({_literal(schema, dialect)})"
    else:
        system = {
            "postgresql": "'pg_catalog', 'information_schema'",
            "redshift": "'pg_catalog', 'information_schema'",
            "mysql": "'mysql', 'information_schema', 'performance_schema', 'sys'",
            "mariadb": "'mysql', 'information_schema', 'performance_schema', 'sys'",
            "sqlserver": "'INFORMATION_SCHEMA', 'sys'",
        }.get(dialect, "'INFORMATION_SCHEMA', 'information_schema'")
        where = f" WHERE {schema_column} NOT IN ({system})"
    if like:
        name_filter = _name_filter(name_column, like, dialect)
        where = f"{where} AND {name_filter}" if where else f" WHERE {name_filter}"
    view = "TABLES" if dialect in ("sqlserver", "bigquery") else "tables"
    return f"SELECT {columns} FROM {source}{view}{where}"


def columns_sql(
    dialect: str, catalog: str | None, schema: str | None, table: str
) -> str:
    if dialect == "postgresql" and not catalog:
        filters = [
            f"UPPER(c.relname) = UPPER({_literal(table, dialect)})",
            "a.attnum > 0",
            "NOT a.attisdropped",
        ]
        if schema:
            filters.append(f"UPPER(n.nspname) = UPPER({_literal(schema, dialect)})")
        return (
            "SELECT n.nspname AS table_schema, a.attnum AS ordinal_position, "
            "a.attname AS column_name, "
            "pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type, "
            "CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable, "
            "has_schema_privilege(n.oid, 'USAGE') "
            "AND has_table_privilege(c.oid, 'SELECT') AS readable "
            "FROM pg_catalog.pg_attribute a "
            "JOIN pg_catalog.pg_class c ON c.oid = a.attrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE {' AND '.join(filters)}"
        )
    if dialect == "sap":
        schema_filter = (
            f" AND UPPER(SCHEMA_NAME) = UPPER({_literal(schema, dialect)})"
            if schema
            else ""
        )
        parts = []
        for source, name in (
            ("SYS.TABLE_COLUMNS", "TABLE_NAME"),
            ("SYS.VIEW_COLUMNS", "VIEW_NAME"),
        ):
            parts.append(
                "SELECT SCHEMA_NAME AS table_schema, POSITION AS ordinal_position, "
                "COLUMN_NAME AS column_name, DATA_TYPE_NAME AS data_type, "
                f"IS_NULLABLE AS is_nullable FROM {source} WHERE UPPER({name}) = "
                f"UPPER({_literal(table, dialect)}){schema_filter}"
            )
        return " UNION ALL ".join(parts)
    source = _catalog_prefix(dialect, catalog, schema)
    upper = dialect == "sqlserver"
    names = [
        "table_schema",
        "ordinal_position",
        "column_name",
        "data_type",
        "is_nullable",
    ]
    columns = ", ".join(n.upper() if upper else n for n in names)
    table_column = "TABLE_NAME" if upper else "table_name"
    schema_column = "TABLE_SCHEMA" if upper else "table_schema"
    filters = [f"UPPER({table_column}) = UPPER({_literal(table, dialect)})"]
    if schema and dialect != "bigquery":
        filters.append(f"UPPER({schema_column}) = UPPER({_literal(schema, dialect)})")
    view = "COLUMNS" if dialect in ("sqlserver", "bigquery") else "columns"
    return f"SELECT {columns} FROM {source}{view} WHERE {' AND '.join(filters)}"


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
    payload = {
        "route": result.route,
        "maxRows": result.max_rows,
        "rowCount": len(result.records),
        "possiblyTruncated": _truncated(result),
        "notes": result.notes,
        "resultSchema": result.schema,
        "columns": result.columns,
        "records": result.records,
    }
    return json.dumps(payload, indent=2, default=str)


def _meta_lines(result: Result) -> list[str]:
    size = f"{len(result.records)} rows x {len(result.columns)} columns"
    if result.route:
        lines = [scrub(f"# route: {result.route} | {size} | maxRows {result.max_rows}")]
    else:
        lines = [f"# {size}"]
    if result.schema:
        types = ", ".join(f"{e.get('name')} {_type_label(e)}" for e in result.schema)
        lines.append(f"# types: {types}")
    lines += [f"# note: {note}" for note in result.notes]
    if _truncated(result):
        lines.append(
            f"# warning: hit maxRows={result.max_rows}; the result is probably "
            "truncated. Narrow the query (WHERE/LIMIT/aggregate) or raise "
            f"--max-rows (max {MAX_ROWS})."
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


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def run_preview(
    client: DataRobotClient,
    conn: Connection,
    sql: str,
    max_rows: int,
    binds: list[Any] | None = None,
) -> Result:
    body: dict[str, Any] = {"jdbcUrl": conn.url, "sql": sql, "maxRows": max_rows}
    if conn.parameters:
        body["parameters"] = conn.parameters
    if binds is not None:
        body["bindParams"] = binds
    try:
        data = _as_dict(
            client.post(PREVIEW_ROUTE, body, timeout=PREVIEW_TIMEOUT, retries=1)
        )
    except ApiError as exc:
        if exc.route_missing:
            raise RouteUnavailable(
                "This DataRobot version has no /jdbcDataPreview/ route "
                "(needs DataRobot 11.7+, API 2.43+)."
            ) from None
        raise
    return Result(
        columns=[str(c) for c in _as_list(data.get("columns"))],
        records=[_as_list(r) for r in _as_list(data.get("records"))],
        route=f"jdbcDataPreview -> {mask_url(conn.url)}",
        max_rows=max_rows,
        schema=[_as_dict(s) for s in _as_list(data.get("resultSchema"))],
    )


def _sort_key(*positions: int) -> Callable[[list[Any]], tuple[Any, ...]]:
    def key(row: list[Any]) -> tuple[Any, ...]:
        values: list[Any] = []
        for position in positions:
            value = row[position] if position < len(row) else None
            text = "" if value is None else str(value)
            values.append((0, int(text)) if text.isdigit() else (1, text.lower()))
        return tuple(values)

    return key


def cmd_check(client: DataRobotClient, args: argparse.Namespace) -> int:
    conn = build_connection(args)
    started = time.monotonic()
    run_preview(client, conn, check_sql(conn.dialect), 1)
    print(
        scrub(
            f"OK: DataRobot reached {mask_url(conn.url)} and logged in, in "
            f"{time.monotonic() - started:.1f} s (driver properties: "
            f"{conn.masked_parameters() or 'none'}). Read access to specific "
            "schemas and tables is not checked."
        )
    )
    return EXIT_OK


EMPTY_NOTE = (
    "no rows: catalog views list only objects this login can access; check the "
    "schema name and its case, and the login's grants"
)


UNREADABLE_NOTE = (
    "readable=False: this login cannot read those objects; ask for USAGE on the "
    "schema and SELECT on the table"
)


def cmd_tables(client: DataRobotClient, args: argparse.Namespace) -> int:
    conn = build_connection(args)
    sql = tables_sql(conn.dialect, args.catalog, args.schema, args.like)
    result = run_preview(client, conn, sql, args.max_rows)
    total = len(result.records)
    cut = _truncated(result)
    needle = (args.like or "").lower()
    result.records = sorted(
        (
            r
            for r in result.records
            if needle in str(r[1] if len(r) > 1 else "").lower()
        ),
        key=_sort_key(0, 1),
    )
    if needle:
        result.notes.append(
            f"{len(result.records)} of {total} fetched names contain {args.like!r}"
        )
        if cut:
            result.notes.append(
                f"the catalog query hit --max-rows {args.max_rows}, so matches may be "
                f"missing: raise --max-rows (max {MAX_ROWS}) or narrow --schema"
            )
    if not total:
        result.notes.append(EMPTY_NOTE)
    if any(len(r) > 3 and str(r[3]) == "False" for r in result.records):
        result.notes.append(UNREADABLE_NOTE)
    return emit(result, args)


def cmd_columns(client: DataRobotClient, args: argparse.Namespace) -> int:
    conn = build_connection(args)
    sql = columns_sql(conn.dialect, args.catalog, args.schema, args.table)
    result = run_preview(client, conn, sql, args.max_rows)
    result.records.sort(key=_sort_key(0, 1))
    if not result.records:
        result.notes.append(EMPTY_NOTE)
    if any(len(r) > 5 and str(r[5]) == "False" for r in result.records):
        result.notes.append(UNREADABLE_NOTE)
    return emit(result, args)


def cmd_query(client: DataRobotClient, args: argparse.Namespace) -> int:
    conn = build_connection(args)
    sql = check_read_only(read_sql(args), lexings_for(conn.dialect))
    binds = parse_binds(args.bind)
    return emit(run_preview(client, conn, sql, args.max_rows, binds), args)


# Statuses that mean the statement never reached the database.
NOT_EXECUTED = frozenset({401, 403, 404, 413, 422})


@dataclass
class WritePlan:
    conn: Connection
    sql: str
    binds: list[Any] | None
    count: int
    warnings: list[str]
    token: str


def build_plan(args: argparse.Namespace) -> WritePlan:
    """Gather what an approval needs. Makes no API call."""
    conn = build_connection(args)
    sql = read_sql(args).strip()
    binds = parse_binds(args.bind)
    count, warnings = analyze_write(sql)
    if not count:
        raise UsageError("SQL is empty.")
    masked = conn.masked_parameters()
    token = plan_token(
        mask_url(conn.url), json.dumps(sorted(masked.items())), sql, json.dumps(binds)
    )
    return WritePlan(conn, sql, binds, count, warnings, token)


PLAN_CHECKS = (
    "Before asking: the script does not inspect the target. Run `check`, confirm "
    "the target exists and is a table, not a view (`tables`, `columns`), and "
    "measure the impact with a read."
)


def print_plan(plan: WritePlan, stale_token: bool = False) -> int:
    conn = plan.conn
    print(
        "WRITE PLAN (nothing has run). Show it to the user and get explicit approval."
    )
    print(PLAN_CHECKS)
    print(scrub(f"  target     : {mask_url(conn.url)} (driver {conn.dialect or '?'})"))
    print(scrub(f"  properties : {conn.masked_parameters() or 'none'}"))
    print(f"  statements : {plan.count}, sent verbatim as one JDBC execute() call")
    print(
        "  atomicity  : driver autocommit, no transaction across statements; "
        "the call has a 30 s server deadline"
    )
    print("  sql:")
    for line in plan.sql.splitlines():
        print(scrub(f"    {line}"))
    if plan.binds is not None:
        print(scrub(f"  binds      : {json.dumps(plan.binds)}"))
    for warning in plan.warnings:
        print(f"  WARNING: {warning}")
    if stale_token:
        print(
            "  NOTE: the --confirm token does not match this plan: the SQL, binds, "
            "URL, or properties changed. Get approval again."
        )
    print(
        "After the user approves this exact plan, run `execute` with the same "
        f"arguments plus --confirm {plan.token}"
    )
    return EXIT_CONFIRM if stale_token else EXIT_OK


def cmd_plan(client: DataRobotClient, args: argparse.Namespace) -> int:
    return print_plan(build_plan(args))


# The SDK's JdbcPreview.preview posts to jdbcPreviewQuery/ from 3.19 on; this
# script never does, but apps moving between SDK versions need to know.
ROUTE_PROBES = (
    (PREVIEW_ROUTE, "check, tables, columns, query"),
    (EXECUTE_ROUTE, "execute"),
    ("jdbcPreviewQuery/", "not this script: SDK 3.19+ JdbcPreview.preview"),
)


def cmd_routes(client: DataRobotClient, args: argparse.Namespace) -> int:
    """Probe each route with a body that fails validation, so no SQL runs."""
    rows = []
    for route, used_by in ROUTE_PROBES:
        binds = ""
        try:
            client.post(route, {"bindParams": []}, timeout=PROBE_TIMEOUT)
            status = "available"
        except ApiError as exc:
            if exc.status == 401:
                raise
            if exc.status == 422:
                status = "available"
                binds = (
                    "no (needs API 2.46)"
                    if "bindParams is not allowed key" in exc.message
                    else "yes"
                )
            elif exc.route_missing:
                status = "missing on this DataRobot version"
            elif exc.status == 403 and "Future Public API" in exc.message:
                status = "not enabled for this account"
            elif exc.status == 403:
                status = "refused for this API token"
            else:
                status = f"HTTP {exc.status}: {exc.message[:80]}"
        rows.append([route.rstrip("/"), used_by, status, binds])
    notes = [
        "probed with requests that fail validation; no SQL ran and no database "
        "was contacted",
        "the answer is for the API token in use; an app's own API key can differ",
    ]
    columns = ["route", "used by", "status", "bind parameters"]
    return emit(Result(columns, rows, notes=notes), args)


def cmd_execute(client: DataRobotClient, args: argparse.Namespace) -> int:
    plan = build_plan(args)
    if args.confirm != plan.token:
        return print_plan(plan, stale_token=True)
    conn, sql, binds, count = plan.conn, plan.sql, plan.binds, plan.count
    body: dict[str, Any] = {"jdbcUrl": conn.url, "sql": sql}
    if conn.parameters:
        body["parameters"] = conn.parameters
    if binds is not None:
        body["bindParams"] = binds
    unknown = (
        "The write may or may not have run. Check with a `query` before "
        "retrying; never re-run blindly."
    )
    try:
        data = client.post(EXECUTE_ROUTE, body, timeout=EXECUTE_TIMEOUT, retries=0)
    except ApiError as exc:
        if exc.route_missing:
            raise RouteUnavailable(
                "This DataRobot version has no /jdbcExecution/ route (needs API 2.45+)."
            ) from None
        reached_database = exc.status not in NOT_EXECUTED and not (
            exc.status == 400 and not exc.message.startswith("SQL [")
        )
        if reached_database:
            print(scrub(f"error: HTTP {exc.status}: {exc.message}"), file=sys.stderr)
            print(f"error: {unknown}", file=sys.stderr)
            return EXIT_API
        raise
    except TransportError as exc:
        print(scrub(f"error: no usable response ({exc}). {unknown}"), file=sys.stderr)
        return EXIT_API
    message = str(_as_dict(data).get("message", ""))
    if message == "OK":
        print(
            scrub(
                f"OK: {count} statement(s) executed on {mask_url(conn.url)}. No row "
                "count is returned; verify the change with `query`."
            )
        )
        return EXIT_OK
    print(scrub(f"FAILED: the database reported: {message}"))
    return EXIT_WRITE_FAILED


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

# Driver wording for a login that works but lacks a grant. MySQL's "Access denied
# for user" is an authentication failure, so it is deliberately not matched.
PRIVILEGE_DENIED = re.compile(
    r"permission denied|permission was denied|command denied to user"
    r"|insufficient.privilege|insufficient_permissions|does not have permission"
    r"|access denied: cannot",
    re.IGNORECASE,
)

HINTS: list[tuple[Callable[[ApiError], bool], str]] = [
    (
        lambda e: e.status == 401,
        "The API token was rejected (the body may be empty): check "
        "DATAROBOT_API_TOKEN or run the datarobot-setup skill.",
    ),
    (
        lambda e: 300 <= e.status < 400,
        "DataRobot answered with a redirect, which the script does not follow "
        "because it would carry the API token elsewhere. Check DATAROBOT_ENDPOINT "
        "(https, host, /api/v2).",
    ),
    (
        lambda e: "No suitable JDBC driver" in e.message,
        "DataRobot has no driver for this URL prefix. Supported prefixes are in "
        "references/jdbc-urls.md.",
    ),
    (
        lambda e: e.status == 403 and bool(PRIVILEGE_DENIED.search(e.message)),
        "The login works but lacks a privilege (see Details). Ask for the grants, "
        "e.g. USAGE on the schema and SELECT on the table.",
    ),
    (
        lambda e: e.status == 403 and "Details:" in e.message,
        "The database rejected the login or a privilege (see Details). For "
        "authentication or password errors check the user and password "
        "properties; otherwise check the grants.",
    ),
    (
        lambda e: "bindParams is not allowed key" in e.message,
        "Bind parameters need DataRobot API 2.46 or later; inline the values as "
        "SQL literals instead.",
    ),
    (
        lambda e: "not allowed key" in e.message,
        "Request fields are camelCase (jdbcUrl, sql, maxRows, parameters, "
        "bindParams); JDBC routes have no credentialId.",
    ),
    (
        lambda e: e.status == 400 and "connection attempt failed" in e.message.lower(),
        "DataRobot could not reach the database. It must be reachable from "
        "DataRobot, not only from your machine: check host, port, and that the "
        "database firewall allows DataRobot.",
    ),
    (
        lambda e: e.status == 408,
        "Over the 300 s preview limit: add WHERE/LIMIT/aggregation, or let a cold "
        "warehouse start and retry.",
    ),
    (lambda e: e.status == 413, "Request over 8 MB: send less SQL or fewer binds."),
    (lambda e: e.status == 429, "Too many concurrent requests; wait and retry."),
    (
        lambda e: e.status == 400 and e.message.startswith("SQL ["),
        "The database rejected the SQL. The preview wraps it as `select * from "
        "(<sql>) _table limit N`; see the dialect limits in references/jdbc-urls.md.",
    ),
]


class _Parser(argparse.ArgumentParser):
    """Usage errors exit with EXIT_USAGE, distinct from API errors."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {scrub(message)}", file=sys.stderr)
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


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    conn = _Parser(add_help=False)
    conn.add_argument("--jdbc-url", help="JDBC URL (prefer --jdbc-url-env for secrets)")
    conn.add_argument(
        "--jdbc-url-env", help="env var with the JDBC URL (default JDBC_URL, JDBC_URI)"
    )
    conn.add_argument(
        "--param", action="append", metavar="KEY=VALUE", help="driver property"
    )
    conn.add_argument(
        "--param-env",
        action="append",
        metavar="KEY=ENV_VAR",
        help="driver property read from an env var (use for secrets)",
    )
    conn.add_argument(
        "--params-json-env",
        metavar="ENV_VAR",
        help="env var holding a JSON object of driver properties "
        "(default JDBC_CONNECTION_PARAMETERS, if set)",
    )
    conn.add_argument(
        "--env-file",
        help="load KEY=VALUE lines (e.g. .env) first, incl. DataRobot auth",
    )

    output = _Parser(add_help=False)
    output.add_argument("--format", choices=("table", "csv", "json"), default="table")
    output.add_argument("--out", help="write all rows to FILE (.csv or .json)")
    output.add_argument(
        "--show",
        type=_int_in(0, 1_000_000),
        default=None,
        help="rows printed (default 100 for tables and columns, 20 otherwise)",
    )
    output.add_argument(
        "--width", type=_int_in(4, 10_000), default=40, help="max table cell width"
    )

    sql = _Parser(add_help=False)
    group = sql.add_mutually_exclusive_group(required=True)
    group.add_argument("--sql", help="SQL text")
    group.add_argument("--sql-file", help="file with the SQL ('-' reads stdin)")
    sql.add_argument("--bind", help="JSON list of values for ? placeholders")

    catalog = _Parser(add_help=False)
    catalog.add_argument("--schema", help="schema (BigQuery: dataset)")
    catalog.add_argument(
        "--catalog",
        help="catalog/database (Snowflake, Databricks, Trino, SQL Server, BigQuery "
        "project)",
    )
    catalog.add_argument("--max-rows", type=_int_in(1, MAX_ROWS), default=1000)

    p = sub.add_parser("check", parents=[conn], help="test the connection")
    p.set_defaults(handler=cmd_check)

    p = sub.add_parser(
        "tables", parents=[conn, catalog, output], help="list tables and views"
    )
    p.add_argument("--like", help="keep tables whose name contains this text")
    p.set_defaults(handler=cmd_tables)

    p = sub.add_parser(
        "columns", parents=[conn, catalog, output], help="list columns of a table"
    )
    p.add_argument("--table", required=True)
    p.set_defaults(handler=cmd_columns)

    p = sub.add_parser(
        "query", parents=[conn, sql, output], help="run one read-only query"
    )
    p.add_argument("--max-rows", type=_int_in(1, MAX_ROWS), default=100)
    p.set_defaults(handler=cmd_query)

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

    p = sub.add_parser(
        "routes",
        parents=[output],
        help="check which JDBC routes this DataRobot and API token can use",
    )
    p.add_argument("--env-file", help="load KEY=VALUE lines first, for DataRobot auth")
    p.set_defaults(handler=cmd_routes)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if getattr(args, "show", 0) is None:
        args.show = 100 if args.handler in (cmd_tables, cmd_columns) else 20
    try:
        if args.env_file:
            load_env_file(args.env_file)
        out = getattr(args, "out", None)
        if out and not Path(out).resolve().parent.is_dir():
            raise UsageError(f"--out directory does not exist: {Path(out).parent}")
        client = DataRobotClient(*load_config())
        return int(args.handler(client, args))
    except UsageError as exc:
        print(scrub(f"error: {exc}"), file=sys.stderr)
        return EXIT_USAGE
    except RouteUnavailable as exc:
        print(scrub(f"unavailable: {exc}"), file=sys.stderr)
        return EXIT_UNAVAILABLE
    except ApiError as exc:
        print(scrub(f"error: HTTP {exc.status}: {exc.message}"), file=sys.stderr)
        for matches, hint in HINTS:
            if matches(exc):
                print(f"hint: {hint}", file=sys.stderr)
                break
        return EXIT_API
    except TransportError as exc:
        print(scrub(f"error: could not reach DataRobot: {exc}"), file=sys.stderr)
        return EXIT_API
    except OSError as exc:
        print(scrub(f"error: {exc}"), file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
