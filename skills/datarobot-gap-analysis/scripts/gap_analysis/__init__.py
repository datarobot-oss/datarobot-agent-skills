# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enterprise-readiness gap analysis engine.

Pillars: Security & Identity (SEC/IDN), AI/LLM Governance (AIG),
Ops & Reliability (OPS/REL), IT Conformance & Regulatory Policy (ITA/POL).

The engine is framework-agnostic. The DataRobot agent (af-component-agent /
LangGraph) wires these functions up as tools; the CLI runs them directly.
"""

from .models import Finding, Severity

__all__ = ["Finding", "Severity"]
__version__ = "0.1.0"
