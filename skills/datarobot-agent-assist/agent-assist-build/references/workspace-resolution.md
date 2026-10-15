## Workspace Resolution

Run after menu options **1** (Design) or **2** (Code). Sets `<target_dir>` for the session.

For menu option **2**, set `<design_to_code>` = false (cold Code entry). **Post-design → code** skips this document — `<design_to_code>` is set in [Post-design next steps](../SKILL.md#post-design-next-steps) before the pre-coding checklist runs.

**Default subdirectory name:** `new-datarobot-agent`

**After resolution:** all design/code work uses `<target_dir>` — specs at `<target_dir>/agent_spec.md`, project `.env` at `<target_dir>/.env`, and helper scripts with `--target-dir <target_dir>` (including `list_llm_models.py`, `rehearsal.py`, and `setup_template.py`). Never create or run `dr dotenv setup` in cwd when `<target_dir>` is a subdirectory.

**On completion** (any path below that sets `<target_dir>`): set `<workspace_resolved>` = true and `<workspace_resolved_target_dir>` = `<target_dir>`.

---

### Path resolution

Use whenever the user must provide a directory that contains `agent_spec.md` (Code entry, or pre-coding Bootstrap step 2 recovery). Referenced from [pre-coding-checklist.md](pre-coding-checklist.md).

1. Ask:

   > Which directory contains your `agent_spec.md`?

2. Do not scan subdirectories automatically. If `./new-datarobot-agent/agent_spec.md` exists, you may mention it as a suggestion — do not set `<target_dir>` without the user's answer.

3. Resolve the user's path (relative paths from cwd). If they give a **file path** (e.g. `./my-agent/agent_spec.md`), use its **parent directory** as the project root.

4. The path must be an **existing directory** containing `agent_spec.md`. If the directory does not exist or has no `agent_spec.md`, ask again.

5. If the user's answer is ambiguous (e.g. "in a subfolder" without a path), ask for the exact directory — do not scan the filesystem to discover specs.

6. Set `<target_dir>` to the resolved directory. Set `<workspace_resolved_target_dir>` = `<target_dir>`. Invalidate `<dependency_check_passed>` (set to false) if it was set.

---

### Decision summary

| Menu | `./agent_spec.md` in cwd? | Action |
|------|---------------------------|--------|
| **Design** | Yes | Set `<target_dir>` = cwd. Ask: continue this spec, or new agent in a subdirectory? |
| **Design** | No | Ask: subdirectory (recommended) or current directory → set `<target_dir>` |
| **Code** | Yes | Ask: is cwd the project root? See [Code — spec found in cwd](#code--spec-found-in-cwd) |
| **Code** | No | Ask for project directory → set `<target_dir>`. No subdir scanning. Pre-coding step 2 will not re-ask for the directory if workspace resolution just set it. |

Option **3** (Deploy) skips this document — see [pre-deployment-checklist.md](pre-deployment-checklist.md).

---

### Design — spec found in cwd

1. Set `<target_dir>` to cwd.
2. Notify: *"Continuing work on `./agent_spec.md` in `<target_dir>`."*
3. Ask:

   > Continue editing this spec, or start a new agent in a subdirectory?

   - **Continue editing** (or "edit" / "this spec") → read `<target_dir>/agent_spec.md`, then read and follow [resume-design.md](resume-design.md).
   - **New agent** (or "new" / "subdirectory") → create/use subdirectory (default `new-datarobot-agent`), set `<target_dir>`, start Design from [Clarification Phase](../SKILL.md#clarification-phase).

### Design — no spec in cwd

Ask:

> Where would you like to design your agent?
> 1. **Subdirectory** (recommended) — e.g. `./new-datarobot-agent`
> 2. **Current directory**

**Subdirectory chosen:**

- Exists with `agent_spec.md` → notify, set `<target_dir>`, read the spec, then read and follow [resume-design.md](resume-design.md).
- Exists without `agent_spec.md` → set `<target_dir>`, start Design from [Clarification Phase](../SKILL.md#clarification-phase).
- Does not exist → create it, set `<target_dir>`, start Design from [Clarification Phase](../SKILL.md#clarification-phase).

**Current directory chosen:**

- Set `<target_dir>` = cwd.
- If paths other than design-phase artifacts are present, set `<design_messy_cwd>` = true and warn. **Allowed without triggering messy cwd:** `agent_spec.md`, `.env`, `.datarobot/rehearsal/` (dress-rehearsal session cache), and `rehearsal_report/rehearsal_report.md`. Any other file or directory (including `.datarobot/answers/`, source code, or unrelated folders) counts as messy.
- If `<design_messy_cwd>` applies:

  > Other files are present. Design can continue here, but coding will require a clean workspace — likely a subdirectory. Files in this directory may be ignored for implementation.

- Start Design from [Clarification Phase](../SKILL.md#clarification-phase).

### Code — spec found in cwd

`./agent_spec.md` exists in cwd, but that alone does not mean cwd is the project root. Ask (exact wording):

> `./agent_spec.md` is in the current directory. Is this your project root?
> 1. **Yes** — use the current directory as the project root
> 2. **No** — the agent is in a different directory

Wait for the user's reply.

- **Choice 1** (or "yes" / "here" / "cwd") → set `<target_dir>` = cwd. Notify: *"Continuing work on `./agent_spec.md` in `<target_dir>`."* Proceed to coding.

- **Choice 2** (or "no" / "subdirectory" / "elsewhere" / "different directory") → follow [Path resolution](#path-resolution). Notify: *"Continuing work on `agent_spec.md` in `<target_dir>`."* Proceed to coding.

### Code — no spec in cwd

The workspace question below **is** Path resolution step 1. After the user answers, continue with [Path resolution](#path-resolution) steps 2–6 only (do not ask again).

Ask:

> Which project directory contains your `agent_spec.md`?

If the user is unsure, remind them the spec may be in a subdirectory (e.g. `./new-datarobot-agent`). If `./new-datarobot-agent/agent_spec.md` exists, you may mention it as a suggestion — do not set `<target_dir>` without the user's answer.

Apply Path resolution steps 2–6 to validate and set `<target_dir>`, then set `<workspace_resolved>` and `<workspace_resolved_target_dir>`.

If no `agent_spec.md` exists at that path, [pre-coding Bootstrap step 2](pre-coding-checklist.md) offers Design or a single directory correction — it will not repeat the workspace directory question verbatim.
