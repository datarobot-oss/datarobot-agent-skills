# AIG-007 — No grounding/citation; hallucination risk

Determine whether factual outputs are grounded in retrieved sources and cited.
Flag agents that answer factual questions purely from model parametric memory
with no retrieval/grounding and no citations, especially in domains where
accuracy matters.

Report the file, line, and the ungrounded generation path.

Output: follow `prompts/_contract.md`.
