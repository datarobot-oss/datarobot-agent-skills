# Fix ITA-005 — Switch to an approved base image

Given the Dockerfile `FROM` line and the policy's `base_images.allow` list,
replace the base image with the closest approved one (preserve the intended
Python version/variant). Update only the `FROM` line(s).

Output: follow `prompts/_fix_contract.md`.
