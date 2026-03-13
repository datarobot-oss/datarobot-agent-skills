
Prep notes for discussing agent loop, skills hub, and related topics.

---

## 1. Agent Loop — Do we plan to add agent-app, OpenClaw, or similar?

**Current state**
- Skills repo = static `SKILL.md` files + helper scripts
- No runtime loop; skills are **instruction context** loaded by agents (Codex, Cursor, Claude, Gemini)
- Agents read SKILL.md → write/run SDK code; skills don’t “execute” in a loop

**Options**

| Option | What it is | Pros | Cons |
|--------|------------|------|------|
| **agent-app** | DataRobot Agent Application template (FastAPI + React + MCP) | Official DR stack, MCP integration | Heavier; skills repo is guidance, not an app |
| **OpenClaw-style loop** | Intake → context → model → tools → stream → persist; skills injected into system prompt | Skills fit naturally; hooks, heartbeat, session mgmt | New runtime to adopt/maintain |
| **LangGraph/PydanticAI** | Programmatic agent with skill loader (see AGENT_FRAMEWORK_INTEGRATION.md) | Lightweight; skills as prompts + tools | Users build their own; we only provide patterns |

**Questions to align on**
- Is the goal to **ship a runnable agent** that uses skills, or keep skills as **reusable guidance** for others’ agents?
- If runnable: agent-app vs OpenClaw vs “reference implementation” in LangGraph?

---

## 2. Skills Hub — How do other agents access/pick skills?

**Current state**
- **Install**: `npx ai-agent-skills install datarobot-oss/datarobot-agent-skills`
- **Claude Code**: `/plugin marketplace add` + `/plugin install <skill>@datarobot-skills`
- **Codex**: AGENTS.md (auto-loaded when workspace is skills repo)
- **Cursor**: AGENTS.md or .cursorrules
- **Gemini**: `gemini extensions install` (gemini-extension.json)
- **LangGraph/PydanticAI**: Manual load via `load_skill()` pattern in docs

**Gaps**
- No central **registry** or **discovery** beyond “clone repo” or “install from GitHub”
- No semantic search (“which skill for X?”)
- No versioning / compatibility checks across agents

**Options**
- **skills.re / AgentSkillsHub / SkillsCatalog**: Publish to external registry (security scan, versioning, multi-agent support)
- **MCP server**: Expose skills as tools; agents call MCP to “get skill X”
- **API / Skills endpoint**: REST or similar for agents to fetch skill content by name/intent
- **Stay GitHub-only**: Keep current install flow; improve AGENTS.md and docs for discovery

**Questions to align on**
- Do we want a **skills hub** (registry/marketplace) or is GitHub + installers enough?
- Who are the main consumers: Cursor/Codex users, or programmatic agents (LangGraph, agent-app)?

---

## 3. Agent loop enabling on-the-fly skill creation, OpenClaw heartbeat, etc.

**If we add an agent loop:**

| Capability | What it means |
|------------|---------------|
| **On-the-fly skill creation** | Agent detects gap (e.g. “no skill for batch scoring”) → generates SKILL.md + scripts → validates → adds to catalog |
| **OpenClaw heartbeat** | Long-running tasks (e.g. AutoML) emit heartbeat events; UI/monitoring can show progress |
| **Dynamic skill selection** | Loop chooses skills at runtime from catalog (vs static AGENTS.md) |
| **Skill composition** | Combine multiple skills in one run (e.g. data-prep → training → deployment) |

**Implication**
- Agent loop is an enabler for these; without it we stay “static guidance only”
- On-the-fly creation needs: generation prompt, validation (e.g. `task validate`), and a place to persist new skills (PR? local? registry?)

---

## 4. Paper you referred to — implications for skills repo

Possible angles depending on the paper:
- **RAG / retrieval**: Skills as retrievable chunks; hub as vector store
- **Tool use / planning**: Skills as tools; agent plans which to call
- **Multi-agent**: Skills as agent roles; composition patterns
- **Evaluation**: How to measure skill quality / agent performance with skills

---

## Summary: Discussion flow

1. **Agent loop**: Do we want a runnable agent in the skills repo, or keep it guidance-only?
2. **Skills hub**: Registry/marketplace vs GitHub + installers?
3. **Loop-enabled features**: On-the-fly creation, heartbeat — are these in scope?
4. **Paper**: Which paper, and what should we change in the repo based on it?
