# Verification of one finding

You are re-checking a single finding another pass produced. You see the cited
file region with `N| ` line prefixes, plus repo-wide grep hints. Decide whether
the finding survives.

Check, in order:
1. Does the cited line (or one within a few lines) contain the code the finding
   describes? If the code is elsewhere in the region, correct `line`.
2. Is the cited code inside a `try/except`, a validator, an allowlist, or a
   type check that already handles the failure the finding describes?
3. Does a nearby comment explain an existing guard? That is evidence the guard
   exists, not that the bug is live.
4. Do the repo-wide hints show the capability the finding says is missing
   (a health endpoint, a JSON log formatter, a timeout on the shared client)?
5. Is the stated impact supported by the code shown, or invented?
6. Is the cited line itself an instance of the capability the finding says is
   missing (a `logger.info` call cited for "no logging", a `timeout=` for "no
   timeout")? Then the finding is refuted.
7. For a secret-exposure finding: is the flagged value a generated credential,
   or an identifier that merely contains a credential-like word (a resource
   URN, a type or class name, a Pulumi target pattern, a placeholder, a
   documentation example, a variable reference)? Identifiers and examples
   refute the finding. Never repeat the value itself in `reason`.

Return ONLY this JSON object:

```json
{
  "verdict": "confirmed | weakened | refuted",
  "reason": "one or two sentences naming the line(s) that decided it",
  "line": 42,
  "severity_overstated": false,
  "remediation_shape": "patch | structural"
}
```

`weakened` means the finding stands but its evidence or impact was overstated;
`refuted` means the code already handles it or the claim is wrong. Set
`severity_overstated` to true only when the real-world consequence is smaller
than the condition's default severity implies; a gap whose evidence was merely
described badly keeps its severity.
`remediation_shape` is `patch` when a few local edits or a setting close the
gap, `structural` when closing it is a workstream (a new harness, a new
component, a deployment change).
