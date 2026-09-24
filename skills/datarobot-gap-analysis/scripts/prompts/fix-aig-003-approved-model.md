# Fix AIG-003 / ITA-003 — Switch to an approved model

Given the unapproved model id, the file, and the policy's `models.allow` list,
replace the model id with the closest approved model (same family/tier when
possible). Update every occurrence in the file. State the chosen replacement in
`explanation`.

Output: follow `prompts/_fix_contract.md`.
