---
name: datarobot-discover
description: >-
  Use when the user wants to find DataRobot capabilities — skills, MCP servers,
  agents, or platform resources — for a task. Fetches the live DataRobot catalog
  directly so results are always current, regardless of third-party search index
  lag. Also checks the user's own DataRobot instance if DATAROBOT_ENDPOINT is set.
---

# Discover DataRobot Resources

Fetch DataRobot catalog and present matching resources for the user's
task. Covers resource types including Global MCP Server. Bring resources once DataRobot publishes them without skill update.

## Step 1 — Fetch the public catalog

```bash
curl -s https://www.datarobot.com/.well-known/ai-catalog.json
```

Always fetch this. It contains all publicly available DataRobot resources.

## Step 2 — Fetch the instance catalog (if DATAROBOT_ENDPOINT is set)

```bash
curl -s \
  -H "Authorization: Bearer $DATAROBOT_API_TOKEN" \
  "$DATAROBOT_ENDPOINT/.well-known/ai-catalog.json"
```

This surfaces resources specific to the user's DataRobot deployment — org-scoped
MCP servers, deployed agents, private tools. If it returns 404, the instance does
not publish a catalog yet; skip silently and continue with the public catalog only.

## Step 3 — Merge and present

Combine both result sets. Deduplicate by `identifier`. Then present as a numbered
list grouped by resource type:

| `type` value | Label |
|---|---|
| `application/ai-skill` | Skill |
| `application/mcp-server+json` | MCP Server |
| `application/ai-agent+json` | Agent |
| anything else | Resource |

For each entry show: **name**, **type**, **description**, and whether it came from
the public catalog or the user's instance. Relevance to the user's task comes
first — don't just dump the full list alphabetically.

## Step 4 — Install guidance (only when the user asks)

Never install or configure anything automatically. When the user picks a result:

**Skill** — install via the DataRobot skills plugin:
```bash
npx ai-agent-skills install <skill-name>
```
Or point directly to the `url` field from the catalog entry (the SKILL.md file).

**MCP Server** — show the MCP connector config using the `url` from the catalog:
```json
{
  "mcpServers": {
    "datarobot": {
      "url": "<url from catalog entry>"
    }
  }
}
```

**Agent** — show the A2A endpoint from the catalog entry and instruct the user
to connect it via their agent framework's standard mechanism.

**Other** — show the `url` and `description` from the catalog entry and let the
user decide how to proceed.
