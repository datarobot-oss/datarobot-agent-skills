## Workspace Resolution

Run after menu options **1** (Design) or **2** (Code). Sets `<target_dir>` for the session.

**Default subdirectory name:** `new-datarobot-agent`

**After resolution:** all design/code work uses `<target_dir>` — specs at `<target_dir>/agent_spec.md`, helper scripts with `--target-dir <target_dir>`, and `list_llm_models.py` / `rehearsal.py` run from `<target_dir>`.

---

### Decision summary

| Menu | `./agent_spec.md` in cwd? | Action |
|------|---------------------------|--------|
| **Design** | Yes | Set `<target_dir>` = cwd. Ask: continue this spec, or new agent in a subdirectory? |
| **Design** | No | Ask: subdirectory (recommended) or current directory → set `<target_dir>` |
| **Code** | Yes | See [Code — spec found in cwd](#code--spec-found-in-cwd) (may redirect to subdirectory) |
| **Code** | No | Ask for project directory path → set `<target_dir>`. No subdir scanning. |

Option **3** (Deploy) skips this document — see [pre-deployment-checklist.md](pre-deployment-checklist.md).

---

### Design — spec found in cwd

1. Set `<target_dir>` to cwd.
2. Notify: *"Continuing work on `./agent_spec.md` in `<target_dir>`."*
3. Ask:

   > Continue editing this spec, or start a new agent in a subdirectory?

   - **Continue editing** → Design in `<target_dir>`.
   - **New agent** → create/use subdirectory (default `new-datarobot-agent`), set `<target_dir>`, Design there.

### Design — no spec in cwd

Ask:

> Where would you like to design your agent?
> 1. **Subdirectory** (recommended) — e.g. `./new-datarobot-agent`
> 2. **Current directory**

**Subdirectory chosen:**

- Exists with `agent_spec.md` → notify, set `<target_dir>`, continue editing.
- Exists without `agent_spec.md` → set `<target_dir>`, continue Design.
- Does not exist → create it, set `<target_dir>`, continue Design.

**Current directory chosen:**

- Set `<target_dir>` = cwd.
- If files other than `agent_spec.md` / `.env` are present, warn:

  > Other files are present. Design can continue here, but coding will require a clean workspace — likely a subdirectory. Files in this directory may be ignored for implementation.

- Continue Design in `<target_dir>`.

### Code — spec found in cwd

1. **Detect active project location** — the spec file alone does not always mean cwd is the project root:

   - If cwd is an **existing template** (git repo, `AGENTS.md` present) → set `<target_dir>` = cwd.
   - Else if cwd contains only `agent_spec.md` and/or `.env` → set `<target_dir>` = cwd.
   - Else if cwd has other files (conflicting workspace) **and** `./new-datarobot-agent/AGENTS.md` exists → set `<target_dir>` = `./new-datarobot-agent`. Notify:

     > Found an implemented agent in `./new-datarobot-agent`. Continuing there. If `./agent_spec.md` also exists in the current directory, it may be outdated — use `<target_dir>/agent_spec.md`.

   - Else → set `<target_dir>` = cwd (pre-coding will handle conflicting workspace).

2. Notify: *"Continuing work on `agent_spec.md` in `<target_dir>`."*
3. Proceed to coding.

### Code — no spec in cwd

Ask:

> Which project directory contains your `agent_spec.md`?

Set `<target_dir>` to the user's answer. Do not scan subdirectories automatically.
