# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lifecycle of a private `dr opencode serve` instance."""

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

_SERVE_STARTUP_SECONDS = 30


def dr_available() -> bool:
    return shutil.which("dr") is not None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class OpenCodeServer:
    """A private `dr opencode serve` on a free localhost port.

    Runs in an empty, git-initialized temp directory: attached sessions take
    their project context from the server's cwd (the caller's cwd would leak
    its AGENTS.md/opencode config into every worker), and opencode's git
    snapshotting silently kills sessions in a git-less directory.
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self.workdir: str | None = None
        self.url: str | None = None

    def start(self) -> str:
        port = _free_port()
        self.workdir = tempfile.mkdtemp(prefix="skills-opencode-")
        subprocess.run(
            ["git", "init", "-q", self.workdir], check=False, capture_output=True
        )
        self._proc = subprocess.Popen(
            ["dr", "opencode", "serve", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.workdir,
        )
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + _SERVE_STARTUP_SECONDS
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                stderr = (self._proc.stderr.read() if self._proc.stderr else "") or ""
                raise RuntimeError(
                    f"dr opencode serve exited {self._proc.returncode}: "
                    f"{stderr.strip()[-500:]}"
                )
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

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self.workdir is not None:
            shutil.rmtree(self.workdir, ignore_errors=True)
            self.workdir = None
        self.url = None

    def __enter__(self) -> "OpenCodeServer":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
