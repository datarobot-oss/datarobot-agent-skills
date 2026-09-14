# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Clone a GitHub repo (or accept a local path) into a workspace."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path


_REMOTE_URL_RE = re.compile(
    r"^(https://[A-Za-z0-9.-]+/[\w.\-~/]+(?:\.git)?/?"
    r"|git@[A-Za-z0-9.-]+:[\w.\-~/]+(?:\.git)?)$"
)


def _auth_url(url: str) -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://github.com/"):
        return url.replace("https://", f"https://x-access-token:{token}@")
    return url


def _validate_remote_url(url: str) -> None:
    """Reject anything that isn't a plain `https://` or `git@` remote.

    Without this, a string such as `--upload-pack=touch /tmp/pwned` is a
    legal `git clone` positional argument that git parses as an option,
    running arbitrary commands as the transport. This skill accepts a
    repo URL directly from the user (or an agent acting on their behalf),
    so the value must be validated before it ever reaches `subprocess`.
    """
    if not _REMOTE_URL_RE.match(url):
        raise ValueError(
            f"'{url}' does not look like a GitHub/git remote URL "
            "(expected https://... or git@...) or an existing local path."
        )


_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$", re.I)


def _validate_ref(ref: str) -> None:
    if ref.startswith("-"):
        raise ValueError(f"'{ref}' is not a valid branch/tag/commit ref.")


def _checkout_commit(dest: str, ref: str) -> None:
    """Fetch and check out a bare commit sha in an already-cloned `dest`.

    `git clone --branch` takes a branch or tag only, so a sha has to be
    fetched after the clone.
    """
    for args in (
        ["fetch", "--depth", "1", "origin", ref],
        ["checkout", "--detach", "FETCH_HEAD"],
    ):
        proc = subprocess.run(
            ["git", "-C", dest, *args], capture_output=True, text=True, timeout=600
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"could not check out commit {ref}: {proc.stderr.strip()[-300:]}"
            )


def clone_repo(url: str, ref: str | None = None, dest: str | None = None) -> str:
    """Return a local workspace path for `url`.

    If `url` is an existing local directory it is returned as-is (no clone).
    Otherwise a shallow clone is made into a temp dir (or `dest`).
    """
    if Path(url).expanduser().is_dir():
        return str(Path(url).expanduser().resolve())

    _validate_remote_url(url)
    if ref:
        _validate_ref(ref)

    dest = dest or tempfile.mkdtemp(prefix="gap-analysis-")
    commit = bool(ref) and bool(_COMMIT_RE.match(str(ref)))
    args = ["git", "clone", "--depth", "1"]
    if ref and not commit:
        args += ["--branch", ref]
    # `--` stops git from ever re-interpreting the URL/dest as options, even
    # if a future change loosens `_validate_remote_url`.
    args += ["--", _auth_url(url), dest]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        # Never leak a token in error text.
        safe = re.sub(r"x-access-token:[^@]+@", "x-access-token:***@", proc.stderr)
        raise RuntimeError(f"git clone failed: {safe.strip()}")
    if commit and ref:
        _checkout_commit(dest, ref)
    return dest
