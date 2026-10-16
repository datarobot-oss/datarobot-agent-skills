# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lifecycle of a private `dr opencode serve` instance."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
from collections.abc import Iterable
import tempfile
import time
from typing import IO
import urllib.error
import urllib.request

from .reasoning import worker_env

_SERVE_STARTUP_SECONDS = 30


def dr_available() -> bool:
    return shutil.which("dr") is not None


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
    snapshotting silently kills sessions in a git-less directory.
    """

    def __init__(
        self, models: Iterable[str] = (), reasoning: str | None = None
    ) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._stderr: IO[str] | None = None
        self.workdir: str | None = None
        self.url: str | None = None
        # Attached sessions inherit the server's config, so reasoning effort
        # for the models workers will use is injected into the server env.
        self.env, self.efforts = worker_env(models, reasoning)

    def start(self) -> str:
        port = _free_port()
        self.workdir = tempfile.mkdtemp(prefix="skills-opencode-")
        subprocess.run(
            ["git", "init", "-q", self.workdir], check=False, capture_output=True
        )
        # Nothing reads the server's stderr for the rest of the run, so a pipe
        # would eventually fill and block the child; a file never does.
        self._stderr = tempfile.TemporaryFile(
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
            env=self.env,
        )
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + _SERVE_STARTUP_SECONDS
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                returncode = self._proc.returncode
                detail = self._stderr_tail()
                self.stop()
                raise RuntimeError(f"dr opencode serve exited {returncode}: {detail}")
            try:
                with urllib.request.urlopen(f"{url}/global/health", timeout=2):
                    self.url = url
                    return url
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.25)
        self.stop()
        raise RuntimeError(
            f"dr opencode serve did not become healthy within {_SERVE_STARTUP_SECONDS}s"
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

    def __enter__(self) -> "OpenCodeServer":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
