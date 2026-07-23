# Plugin sandbox

A throwaway environment for checking a **Claude Code marketplace plugin** end to
end — without touching your real `~/.claude` config or the plugins in your
everyday sessions.

`check-plugin.sh` runs against its own isolated `CLAUDE_CONFIG_DIR`
(`sandbox/.claude-config/`, git-ignored), so every run is reproducible and
disposable. By default it checks **this repository's** plugin
(`datarobot-agent-skills`), but you can point it at any local directory, GitHub
repo, or marketplace URL.

## What it does

1. **Validate** the plugin/marketplace manifest (`claude plugin validate`).
2. **Add** the marketplace into the isolated sandbox config.
3. **Resolve & install** the plugin (auto-detected, or picked with `--plugin`).
4. **Inspect** the installed plugin — component inventory (skills, agents,
   hooks, MCP servers) and projected token cost (`claude plugin details`).
5. Optionally **launch** a live Claude Code session with only that plugin
   loaded, so you can type a trigger phrase and watch a skill fire.

## Prerequisites

- The `claude` CLI on your `PATH` (`claude --version`).

## Usage

```bash
# Check this repo's plugin (the default)
sandbox/check-plugin.sh

# ...or via Taskfile
task sandbox

# Check a local plugin you're developing
sandbox/check-plugin.sh --source ../my-plugin

# Check a plugin published on GitHub
sandbox/check-plugin.sh --source datarobot-oss/datarobot-agent-skills

# Check, then drop into a live session to test triggering
sandbox/check-plugin.sh --launch
```

### Options

| Flag | Meaning |
| --- | --- |
| `-s, --source <path\|url\|owner/repo>` | Marketplace/plugin source. Default: this repo. |
| `-p, --plugin <name>` | Which plugin to install (when a marketplace has more than one). |
| `-m, --marketplace <name>` | Marketplace name (auto-detected if omitted). |
| `-l, --launch` | Open a live Claude Code session after the check. |
| `--keep` | Reuse the existing sandbox config instead of wiping it. |
| `-h, --help` | Show help. |

Pass flags through the Taskfile after `--`, e.g.
`task sandbox -- --source ../my-plugin --launch`.

## Testing that skills actually trigger

The check confirms the plugin *installs and loads*. To confirm a skill *fires*,
open the live session and prompt it with a phrase the skill's `description`
targets:

```bash
sandbox/check-plugin.sh --launch
```

Then, for example, ask something that should activate a DataRobot skill and
confirm the expected skill loads. Press `Ctrl-D` or type `/exit` to leave the
sandbox; nothing you did there affects your normal Claude Code config.

## Cleaning up

Everything the sandbox creates lives under `sandbox/.claude-config/` and
`sandbox/.workdir/` and is git-ignored. Delete them (or re-run without
`--keep`) to reset:

```bash
rm -rf sandbox/.claude-config sandbox/.workdir
```
