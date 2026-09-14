# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Selectable Pulumi configuration variants: which inactive one already
declares a deployment, and how to select it. Shared by the posture advice and
the Layer 4 prerequisites, so it lives apart from both."""

from __future__ import annotations

from typing import Any


def shipped_deployment_variant(iac: dict[str, Any] | None) -> str | None:
    """An inactive configuration variant that declares a datarobot.Deployment,
    when the active one does not: selecting it is the remedy, not new IaC."""
    iac = iac or {}
    if iac.get("deployment"):
        return None
    candidates: list[str] = [
        str(rel)
        for rel, found in (iac.get("inactive_variants") or {}).items()
        if found.get("deployment")
    ]
    if not candidates:
        return None
    # A gateway-backed variant keeps the LLM provider the org already governs.
    return min(candidates, key=_prefer_gateway)


def _prefer_gateway(rel: str) -> tuple[bool, str]:
    return ("gateway" not in rel.lower(), rel)


def _select_variant_text(iac: dict[str, Any], variant: str) -> str:
    selector = iac.get("variant_selector")
    how = (
        f"set {selector}={variant.rsplit('/', 1)[-1]}"
        if selector
        else "point the configuration symlink at it"
    )
    return (
        f"This repo already ships a variant that declares one: {variant}. "
        f"Select it ({how}) instead of writing new infrastructure."
    )
