# Fix AIG-002 - Pin a floating model id

Given the floating model id, the file, and the list of model ids the org's
DataRobot LLM Gateway serves (when provided), replace the alias with the pinned
id from that list that carries a date or version suffix and belongs to the same
family. If the gateway list is empty or has no pinned id for the family, return
`can_fix: false` and explain which pinned id the human should choose; never
invent an id. Update every occurrence in the file.

Output: follow `prompts/_fix_contract.md`.
