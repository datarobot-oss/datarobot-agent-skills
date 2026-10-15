# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read the verdict of an LLM skill review.

datarobot-agent-tester's parser expects a `###` heading. When the judge writes
`## Overall Verdict`, it falls back to scanning the whole report and fails a
skill rated NEEDS WORK because the prose says "incomplete" (see
datarobot-agent-tester PR #9). This parser accepts any heading level and never
reads the report body. Drop it once that fix is released.
"""

from __future__ import annotations

import re

VERDICTS = ("INCOMPLETE", "NEEDS WORK", "GOOD")
UNKNOWN = "UNKNOWN"

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*overall\s+verdict\s*:?\s*(.*)$", re.IGNORECASE)
_BOLD_LABEL = re.compile(
    r"^\s*\*\*\s*overall\s+verdict\s*:?\s*\*\*\s*:?\s*(.*)$", re.IGNORECASE
)
_SEPARATOR = re.compile(r"\s+[—–-]\s+|\s*[—–]\s*|:")


def parse_verdict(report: str) -> str:
    """Return GOOD, NEEDS WORK, INCOMPLETE, or UNKNOWN when no verdict line exists.

    The last "Overall verdict" section wins. The verdict is the label before the
    first dash, so "NEEDS WORK — the guards are incomplete" reads as NEEDS WORK.
    """
    lines = report.splitlines()
    text: str | None = None
    for index, line in enumerate(lines):
        match = _HEADING.match(line) or _BOLD_LABEL.match(line)
        if not match:
            continue
        inline = match.group(1).strip()
        following = next(
            (rest.strip() for rest in lines[index + 1 :] if rest.strip()), ""
        )
        text = inline or following
    if text is None:
        return UNKNOWN

    label = _SEPARATOR.split(re.sub(r"[*_`]", "", text), maxsplit=1)[0]
    label = re.sub(r"[-\s]+", " ", label).strip().upper()
    found = [(label.find(verdict), verdict) for verdict in VERDICTS if verdict in label]
    return min(found)[1] if found else UNKNOWN
