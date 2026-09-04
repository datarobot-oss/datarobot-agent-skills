# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Clone a GitHub repo (or accept a local path) into a workspace."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path


def _auth_url(url: str) -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://github.com/"):
        return url.replace("https://", f"https://x-access-token:{token}@")
    return url


def clone_repo(url: str, ref: str | None = None, dest: str | None = None) -> str:
    """Return a local workspace path for `url`.

    If `url` is an existing local directory it is returned as-is (no clone).
    Otherwise a shallow clone is made into a temp dir (or `dest`).
    """
    if Path(url).expanduser().is_dir():
        return str(Path(url).expanduser().resolve())

    dest = dest or tempfile.mkdtemp(prefix="gap-analysis-")
    args = ["git", "clone", "--depth", "1"]
    if ref:
        args += ["--branch", ref]
    args += [_auth_url(url), dest]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        # Never leak a token in error text.
        safe = re.sub(r"x-access-token:[^@]+@", "x-access-token:***@", proc.stderr)
        raise RuntimeError(f"git clone failed: {safe.strip()}")
    return dest
