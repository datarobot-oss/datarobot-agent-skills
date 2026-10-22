# AIG-001 — No guardrails (toxicity / PII / jailbreak / output filtering)

Determine whether model inputs and outputs pass through any guardrail layer:
moderation/toxicity checks, PII detection/redaction, jailbreak/prompt-injection
detection, or output schema/content validation. Flag agents that send user
input straight to the model and return raw output with none of these.

Report the file, line, and what protection is missing.

Output: follow `prompts/_contract.md`.
