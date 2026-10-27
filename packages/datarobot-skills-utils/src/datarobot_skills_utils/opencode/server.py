# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lifecycle of a private `dr opencode serve` instance."""

from __future__ import annotations

import base64
import http.client
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from typing import IO, Self

from .events import usage_meta
from .reasoning import worker_env
from .version import opencode_version

_SERVE_STARTUP_SECONDS = 30


def dr_available() -> bool:
    return shutil.which("dr") is not None


def _get(url: str, password: str | None = None, timeout: float = 10) -> bytes:
    """GET `url`, with the basic auth an opencode server expects when it has a
    password (the user name is always `opencode`)."""
    request = urllib.request.Request(url)
    if password:
        token = base64.b64encode(f"opencode:{password}".encode()).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body: bytes = response.read()
        return body


def session_usage(
    server_url: str, session: str | None, password: str | None, timeout: float = 10
) -> dict[str, object] | None:
    """Token meta of one session on an opencode 2.x server, summed over its
    assistant messages, or None when it cannot be read (usage is optional)."""
    if not session:
        return None
    path = urllib.parse.quote(session, safe="")
    url = f"{server_url}/api/session/{path}/message?type=assistant&limit=200"
    try:
        body = json.loads(_get(url, password, timeout))
    except (http.client.HTTPException, OSError, ValueError):
        return None
    messages = body.get("data") if isinstance(body, dict) else None
    return usage_meta(messages) if isinstance(messages, list) else None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _own_group(proc: subprocess.Popen[str]) -> int | None:
    """The child's private process group, or None when there is not one to
    signal: Windows has no process groups here, and a child that shares the
    caller's group must never be signalled as a group, since that would take
    the caller down with it.
    """
    if not hasattr(os, "getpgid") or not hasattr(os, "killpg"):
        return None
    try:
        pgid = os.getpgid(proc.pid)
        return None if pgid == os.getpgid(0) else pgid
    except (ProcessLookupError, PermissionError, OSError):
        return None


def terminate_process_tree(proc: subprocess.Popen[str], timeout: float = 5.0) -> None:
    """Stop `proc` and every descendant started with `start_new_session=True`.

    Terminating only the direct child leaves re-exec'd grandchildren running,
    which is how orphaned servers accumulate across runs. Where the platform
    has no process groups, only the direct child can be stopped.
    """
    pgid = _own_group(proc)
    # Windows has no SIGKILL; there, both rounds end in TerminateProcess.
    hard = getattr(signal, "SIGKILL", signal.SIGTERM)
    for sig in (signal.SIGTERM, hard):
        if pgid is not None:
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError):
                pass
        else:
            proc.send_signal(sig)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        break
    if pgid is None:
        return
    # Grandchildren can outlive the wrapper by a moment; give the group a
    # few polls to drain before the hard signal is left as the last word above.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.1)
    try:
        os.killpg(pgid, hard)
    except (ProcessLookupError, PermissionError):
        pass


class OpenCodeServer:
    """A private `dr opencode serve` on a free localhost port.

    Runs in an empty, git-initialized temp directory: attached sessions take
    their project context from the server's cwd (the caller's cwd would leak
    its AGENTS.md/opencode config into every worker), and opencode's git
    snapshotting silently kills sessions in a git-less directory. With
    opencode 2.x the server also gets a random `password`, which workers
    attaching to it must pass to run_worker; opencode 2.x workers should also
    run with `cwd=workdir`, since 2.x takes a session's directory from the
    worker, not the server.
    """

    def __init__(
        self, models: Iterable[str] = (), reasoning: str | None = None
    ) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._stderr: IO[str] | None = None
        self.workdir: str | None = None
        self.url: str | None = None
        self.password: str | None = None
        # Attached sessions inherit the server's config, so reasoning effort
        # for the models workers will use is injected into the server env.
        self.env, self.efforts = worker_env(models, reasoning)

    def start(self) -> str:
        port = _free_port()
        self.workdir = tempfile.mkdtemp(prefix="skills-opencode-")
        subprocess.run(
            ["git", "init", "-q", self.workdir], check=False, capture_output=True
        )
        version = opencode_version()
        env, health = self.env, "/global/health"
        if version.major >= 2:
            # 2.x always guards its API with a password and makes one up (and
            # prints it) when the environment has none, so set our own.
            self.password = secrets.token_urlsafe(32)
            env = {**self.env, "OPENCODE_PASSWORD": self.password, "PWD": self.workdir}
            # 2.x answers /global/health with its web app before the API is up.
            health = "/api/info"
        # Nothing reads the server's stderr for the rest of the run, so a pipe
        # would eventually fill and block the child; a file never does.
        self._stderr = tempfile.TemporaryFile(  # noqa: SIM115 - lives until stop() closes it
            mode="w+", encoding="utf-8", errors="replace"
        )
        # `dr opencode serve` re-execs the real server twice; a fresh session puts
        # the whole chain in one process group so stop() can take it all down.
        self._proc = subprocess.Popen(
            ["dr", "opencode", "serve", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=self._stderr,
            text=True,
            cwd=self.workdir,
            start_new_session=True,
            env=env,
        )
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + _SERVE_STARTUP_SECONDS
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                returncode = self._proc.returncode
                detail = self._stderr_tail()
                self.stop()
                raise RuntimeError(
                    f"dr opencode serve exited {returncode}: {detail} "
                    f"({version.describe()})"
                )
            try:
                _get(f"{url}{health}", self.password, timeout=2)
                self.url = url
                return url
            except (http.client.HTTPException, OSError):
                time.sleep(0.25)
        self.stop()
        raise RuntimeError(
            f"dr opencode serve did not become healthy within {_SERVE_STARTUP_SECONDS}s "
            f"({version.describe()})"
        )

    def _stderr_tail(self, limit: int = 500) -> str:
        if self._stderr is None:
            return ""
        try:
            self._stderr.seek(0)
            return self._stderr.read().strip()[-limit:]
        except (OSError, ValueError):
            return ""

    def stop(self) -> None:
        if self._proc is not None:
            terminate_process_tree(self._proc)
            self._proc = None
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None
        if self.workdir is not None:
            shutil.rmtree(self.workdir, ignore_errors=True)
            self.workdir = None
        self.url = None
        self.password = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
