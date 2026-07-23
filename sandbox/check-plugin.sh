#!/usr/bin/env bash
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# check-plugin.sh — spin up an isolated Claude Code sandbox to check a Claude
# marketplace plugin end to end:
#
#   1. validate the plugin/marketplace manifest
#   2. add the marketplace
#   3. install the plugin
#   4. print its component inventory + projected token cost
#   5. (optional) drop you into a live session with the plugin loaded
#
# The sandbox runs against its own CLAUDE_CONFIG_DIR (sandbox/.claude-config),
# so it never touches your real ~/.claude config or the plugins in your normal
# sessions. Each run starts from a clean sandbox for a reproducible check.
#
# Usage:
#   sandbox/check-plugin.sh                       # check this repo's plugin
#   sandbox/check-plugin.sh --source ../my-plugin # check a local plugin dir
#   sandbox/check-plugin.sh --source owner/repo   # check a plugin from GitHub
#   sandbox/check-plugin.sh --plugin NAME         # pick a plugin by name
#   sandbox/check-plugin.sh --launch              # then open a live session
#   sandbox/check-plugin.sh --keep                # reuse an existing sandbox
#
# Run with --help for the full option list.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_DIR="$SCRIPT_DIR/.claude-config"
WORK_DIR="$SCRIPT_DIR/.workdir"

# --- defaults ----------------------------------------------------------------
SOURCE="$REPO_ROOT"   # what to check; defaults to this repo's plugin
PLUGIN=""             # plugin name (auto-detected when a marketplace has one)
MARKETPLACE=""        # marketplace name (auto-detected from the source)
LAUNCH=0              # open an interactive session after the check
KEEP=0                # reuse the existing sandbox instead of wiping it

# --- pretty output -----------------------------------------------------------
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; RED=$'\033[31m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; GREEN=""; RED=""; YELLOW=""; BLUE=""; RESET=""
fi

step()  { printf '\n%s==> %s%s\n' "$BOLD$BLUE" "$*" "$RESET"; }
ok()    { printf '%s✓ %s%s\n' "$GREEN" "$*" "$RESET"; }
warn()  { printf '%s! %s%s\n' "$YELLOW" "$*" "$RESET"; }
die()   { printf '%s✗ %s%s\n' "$RED" "$*" "$RESET" >&2; exit 1; }

usage() {
  cat <<'EOF'
check-plugin.sh — check a Claude marketplace plugin in an isolated sandbox

Options:
  -s, --source <path|url|owner/repo>  Marketplace/plugin source to check.
                                      Default: this repository's plugin.
  -p, --plugin <name>                 Plugin to install (needed when a
                                      marketplace exposes more than one).
  -m, --marketplace <name>            Marketplace name (auto-detected if omitted).
  -l, --launch                        Open a live Claude Code session with the
                                      plugin loaded so you can test triggering.
      --keep                          Reuse the existing sandbox config instead
                                      of wiping it for a fresh run.
  -h, --help                          Show this help and exit.

Examples:
  sandbox/check-plugin.sh
  sandbox/check-plugin.sh --source ../my-plugin --launch
  sandbox/check-plugin.sh --source datarobot-oss/datarobot-agent-skills
EOF
}

# --- argument parsing --------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--source)      [[ $# -ge 2 ]] || die "$1 needs a value"; SOURCE="$2"; shift 2 ;;
    -p|--plugin)      [[ $# -ge 2 ]] || die "$1 needs a value"; PLUGIN="$2"; shift 2 ;;
    -m|--marketplace) [[ $# -ge 2 ]] || die "$1 needs a value"; MARKETPLACE="$2"; shift 2 ;;
    -l|--launch)      LAUNCH=1; shift ;;
    --keep)           KEEP=1; shift ;;
    -h|--help)        usage; exit 0 ;;
    *)                die "Unknown option: $1 (see --help)" ;;
  esac
done

command -v claude >/dev/null 2>&1 || die "The 'claude' CLI is not on PATH. Install Claude Code first."

# A local directory source is resolved to an absolute path so the CLI is happy
# regardless of the sandbox's working directory.
if [[ -d "$SOURCE" ]]; then
  SOURCE="$(cd "$SOURCE" && pwd)"
fi

# --- isolate the sandbox -----------------------------------------------------
if [[ "$KEEP" -eq 0 ]]; then
  rm -rf "$CONFIG_DIR"
fi
mkdir -p "$CONFIG_DIR" "$WORK_DIR"
export CLAUDE_CONFIG_DIR="$CONFIG_DIR"

printf '%sClaude marketplace plugin sandbox%s\n' "$BOLD" "$RESET"
printf '  %ssource     %s %s\n' "$DIM" "$RESET" "$SOURCE"
printf '  %sconfig dir %s %s\n' "$DIM" "$RESET" "$CONFIG_DIR"

# --- 1. validate the manifest ------------------------------------------------
step "Validating manifest"
if claude plugin validate "$SOURCE"; then
  ok "Manifest valid"
else
  die "Manifest validation failed — fix the errors above before installing."
fi

# --- 2. add the marketplace --------------------------------------------------
step "Adding marketplace"
claude plugin marketplace add "$SOURCE"

# --- 3. resolve which plugin to install --------------------------------------
# Ask the CLI what the freshly added marketplace exposes and pick a plugin.
AVAILABLE_JSON="$(claude plugin list --available --json 2>/dev/null || echo '{}')"
PLUGIN_ID="$(
  AVAILABLE_JSON="$AVAILABLE_JSON" PLUGIN="$PLUGIN" MARKETPLACE="$MARKETPLACE" \
  python3 <<'PY'
import json, os, sys

data = json.loads(os.environ.get("AVAILABLE_JSON") or "{}")
avail = data.get("available", [])
want_plugin = os.environ.get("PLUGIN") or ""
want_market = os.environ.get("MARKETPLACE") or ""

def matches(entry):
    if want_plugin and entry.get("name") != want_plugin:
        return False
    if want_market and entry.get("marketplaceName") != want_market:
        return False
    return True

candidates = [e for e in avail if matches(entry=e)]

if not candidates:
    sys.stderr.write("No matching plugin found in the added marketplace.\n")
    if avail:
        sys.stderr.write("Available plugins:\n")
        for e in avail:
            sys.stderr.write(f"  - {e.get('pluginId')}\n")
    sys.exit(2)

if len(candidates) > 1:
    sys.stderr.write("Multiple plugins available — pick one with --plugin:\n")
    for e in candidates:
        sys.stderr.write(f"  - {e.get('pluginId')}\n")
    sys.exit(3)

print(candidates[0]["pluginId"])
PY
)" || die "Could not resolve a plugin to install (see above)."

ok "Selected plugin: $PLUGIN_ID"

# --- 4. install + inspect ----------------------------------------------------
step "Installing $PLUGIN_ID"
claude plugin install "$PLUGIN_ID" --scope user
ok "Installed"

step "Installed plugins"
claude plugin list

step "Component inventory & token cost"
PLUGIN_NAME="${PLUGIN_ID%@*}"
claude plugin details "$PLUGIN_NAME"

# --- 5. summary + optional live session --------------------------------------
step "Sandbox ready"
cat <<EOF
The plugin is installed in an isolated config at:
  $CONFIG_DIR

To open a live Claude Code session with ONLY this plugin loaded and try a
trigger phrase, run:

  ${BOLD}CLAUDE_CONFIG_DIR="$CONFIG_DIR" claude${RESET}

Re-run this script any time for a clean check (use --keep to reuse the sandbox).
EOF

if [[ "$LAUNCH" -eq 1 ]]; then
  step "Launching live session (Ctrl-D or /exit to leave the sandbox)"
  cd "$WORK_DIR"
  exec claude
fi
