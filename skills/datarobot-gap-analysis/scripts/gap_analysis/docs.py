# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve DataRobot documentation pages at run time.

docs.datarobot.com publishes an llms.txt index (one `- [Title](URL): summary`
line per page). Mitigations name a docs *topic*; the matching page is looked up
here so the report never carries a pinned URL that can go stale. Offline, the
topic is shown as a search hint instead of a link.
"""

from __future__ import annotations

import os
import re
import urllib.request

LLMS_TXT_URL = "https://docs.datarobot.com/llms.txt"
_LINE_RE = re.compile(r"^- \[([^\]]+)\]\((https?://[^)]+)\)(?::\s*(.*))?$", re.M)
_WORD_RE = re.compile(r"[a-z0-9]+")
# Classic UI, API reference and release notes describe the feature but are not
# where a user goes to configure it; prefer the current product pages.
_DEPRIORITIZED_PATHS = ("/classic-ui/", "/api/", "/release/")
_STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "for",
    "to",
    "in",
    "on",
    "with",
    "datarobot",
}

_index_cache: list[tuple[str, str, str]] | None = None


def parse_llms_txt(text: str) -> list[tuple[str, str, str]]:
    """[(title, url, summary)] for every page line in an llms.txt document."""
    return [
        (m.group(1).strip(), m.group(2).strip(), (m.group(3) or "").strip())
        for m in _LINE_RE.finditer(text)
    ]


def docs_index() -> list[tuple[str, str, str]]:
    """The live page index, fetched once per process; empty when offline or
    disabled with GAP_DOCS_CATALOG=off."""
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    _index_cache = []
    if os.environ.get("GAP_DOCS_CATALOG", "").lower() != "off":
        try:
            with urllib.request.urlopen(LLMS_TXT_URL, timeout=8) as resp:
                _index_cache = parse_llms_txt(resp.read().decode("utf-8", "ignore"))
        except (OSError, ValueError):
            _index_cache = []
    return _index_cache


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP}


def resolve_docs(topic: str, index: list[tuple[str, str, str]] | None = None) -> str:
    """URL of the docs page that best matches `topic`, or "" when nothing fits.

    Title matches count double; a page must cover at least half of the topic's
    words so a vague topic does not pick an arbitrary page.
    """
    want = _tokens(topic)
    if not want:
        return ""
    best_url, best_score = "", 0.0
    for title, url, summary in index if index is not None else docs_index():
        title_hits = len(want & _tokens(title))
        score = 2.0 * title_hits + len(want & _tokens(summary))
        if title_hits == len(want):
            score += 3  # the title says exactly what the topic asks for
        if any(part in url for part in _DEPRIORITIZED_PATHS):
            score -= 1.5
        if score > best_score:
            best_url, best_score = url, score
    return best_url if best_score / (2 * len(want)) >= 0.5 else ""
