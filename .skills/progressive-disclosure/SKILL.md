---
name: progressive-disclosure
description: Refactor large DataRobot skill files by moving detailed content into directly linked reference files while preserving meaning. Use when a skill triggers context-window warnings, needs progressive disclosure, or should be chunked without changing guidance.
---

# Progressive Disclosure

Use this repo-local meta skill to split large skills into a concise `SKILL.md` plus adjacent reference files. This guides content moves and reference creation; it is not a content rewrite pass.

## Guardrails

- Do not rewrite, reinterpret, simplify, or change the meaning of skill content.
- Do not delete details because they seem verbose. Move details to reference files instead.
- Do not change SDK guidance, commands, workflows, safety notes, or examples except to preserve links after moving content.
- Do not edit plugin manifests, versions, `CODEOWNERS`, or unrelated repo metadata unless the user explicitly asks.
- Do not create deeply nested references. Reference files should be direct siblings of `SKILL.md`.
- Do not move first-use trigger guidance, required safety constraints, or critical prerequisites out of `SKILL.md`.
- If content needs substantive editing, stop and ask the user before making that change.

## Target Shape

Keep `SKILL.md` focused on:

- Frontmatter with accurate `name` and `description`
- When to use the skill
- Quick start or primary workflow
- Key decision points and safety constraints
- Direct links to reference files

Move long supporting content into files such as:

- `reference.md`
- `examples.md`
- `troubleshooting.md`
- `platform-setup.md`
- `sdk-operations.md`
- `ci-cd-patterns.md`

Choose names that match the moved section. Prefer a small number of meaningful files over many tiny fragments.

## Workflow

1. Inspect the target skill:
   - Read `skills/<skill-name>/SKILL.md`.
   - Check current line count and major headings.
   - Check current token warning/error status from `task test:integration` when available.
   - Identify sections that are detailed reference material, long examples, command recipes, troubleshooting tables, platform-specific variants, or API details.

2. Propose the split before editing when the change is substantial:
   - List which sections will stay in `SKILL.md`.
   - List which sections will move and the destination reference file for each.
   - Keep a simple traceability map: original heading -> destination file -> replacement link text.
   - Confirm any ambiguous sections with the user.

3. Move content with minimal transformation:
   - Preserve headings and body text as much as possible.
   - Adjust heading levels only when needed for valid Markdown structure.
   - Preserve code blocks exactly unless a relative link/path must change.
   - Keep warnings, prerequisites, and safety notes attached to the relevant content.

4. Replace moved content with concise pointers:

   ```markdown
   For detailed deployment configuration, see [deployment-reference.md](deployment-reference.md).
   ```

   Each pointer should explain when to read the reference, not summarize the whole reference.

5. Keep links one level deep:
   - `SKILL.md` should link directly to every reference file the agent may need.
   - Reference files may link back to `SKILL.md` if useful.
   - Avoid chains like `SKILL.md` -> `reference.md` -> `deep-reference.md`.

6. Validate:
   - Run `task test:integration` for structural checks.
   - Run `task lint` when tooling is available.
   - If the goal is reducing context-window warnings, rerun the relevant tests and compare warning output. This repo warns at an estimated 3300 tokens and errors at 6700 tokens.

## Candidate Section Heuristics

Good move candidates:

- Long examples that are not needed for initial task routing
- Repeated setup variants by platform or provider
- Detailed SDK method inventories
- Troubleshooting catalogs
- Extended CI/CD snippets
- Long validation or debugging procedures

Usually keep in `SKILL.md`:

- The first-pass decision tree
- Required safety constraints
- Minimal happy-path workflow
- Short command checklist needed for most runs
- Links to all supporting references

## Diff Review Checklist

Before finishing, verify:

- Every moved block still exists in a reference file.
- `SKILL.md` links directly to each new reference file.
- The frontmatter `description` still includes clear trigger scenarios.
- The final response includes the traceability map for reviewer confidence.
- No instruction, recommendation, or example changed.
- No unrelated formatting churn was introduced.
- Repo validation passes or any local tooling gap is clearly reported.
