#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic helpers for clustering breaches and applying prompt patches."""

import re
import string


def normalize_breach(text: str) -> str:
    """Normalize a breach reason into a stable clustering key."""
    if not text:
        return ""
    words = text.split()
    filtered = []
    sentence_start = True
    for word in words:
        clean = word.strip(string.punctuation)
        if clean and clean[0].isupper() and not sentence_start:
            pass
        else:
            filtered.append(word.lower())
        sentence_start = bool(re.search(r"[.!?]\s*$", word))
    normalized = " ".join(filtered)
    normalized = re.sub(r"\d+", "", normalized)
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def apply_system_prompt_patch(current_prompt: str, patch: str) -> str:
    """Append a validated prompt patch while preserving existing behavior."""
    return current_prompt + "\n" + patch
