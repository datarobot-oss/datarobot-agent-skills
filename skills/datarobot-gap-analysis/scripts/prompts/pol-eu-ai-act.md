# EU AI Act — Regulatory Control Mapping (Layer 4)

This single file backs POL-001..POL-007. The orchestrator runs the section
matching the `#anchor` in the condition's `detector`. Each section is evidence-
based: look across docs (`README`, `docs/`, model cards) AND code for evidence
that the obligation is met; if none is found, report it as a gap with
`status: "found"` (the gap exists) and cite where you looked.

Context: EU AI Act obligations for general-purpose AI (GPAI) apply from
August 2025; high-risk-system obligations apply from August 2026. Findings are
advisory and do not constitute legal advice.

Output for every section: follow `prompts/_contract.md`, using the matching
`condition_id`.

## risk-classification {#risk-classification}
Look for any documented determination of the system's EU AI Act risk tier
(prohibited / high-risk / limited / minimal) or GPAI status, and the reasoning.
Gap if no such classification is documented anywhere.

## transparency {#transparency}
Look for evidence that end users are informed they are interacting with an AI
system, and that AI-generated/manipulated content is marked/disclosed where
required (Art. 50). Gap if user-facing AI interaction has no disclosure.

## technical-documentation {#technical-documentation}
Look for technical documentation in the spirit of Annex IV: intended purpose,
system design/architecture, data used, capabilities and limitations, and known
risks. A model card counts. Gap if substantively absent.

## record-keeping {#record-keeping}
Look for automatic logging/event recording sufficient for traceability across
the system lifecycle (Art. 12). Cross-reference OPS-001/OPS-002. Gap if no
lifecycle event logging exists.

## human-oversight {#human-oversight}
Look for human oversight/intervention mechanisms over the system's operation
(Art. 14): ability to monitor, intervene, override, or stop. Cross-reference
AIG-005. Gap if none.

## accuracy-robustness {#accuracy-robustness}
Look for evidence of accuracy metrics, robustness/adversarial testing, and
cybersecurity measures appropriate to the system (Art. 15). Gap if no such
evidence exists.

## prohibited-practices {#prohibited-practices}
Screen for indicators of an Art. 5 prohibited practice: social scoring,
subliminal/manipulative or exploitative techniques, untargeted scraping of
facial images, biometric categorization inferring sensitive attributes,
real-time remote biometric identification in public spaces, emotion inference
in workplace/education. Any indicator is a critical finding; recommend legal
review. Gap status `not_found` only if clearly none apply.
