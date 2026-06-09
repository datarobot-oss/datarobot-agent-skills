---
name: datarobot-setup
description: Sets up DataRobot for local development including Python SDK, dr-cli, Agent Assist, and all required dependencies. Use when the user has not yet worked with DataRobot on this machine, OR when any DataRobot task fails due to missing or invalid credentials. Covers first-time setup, re-authentication, and credential recovery.
---

# DataRobot Local Development Setup

You are helping set up DataRobot for local development. Before installing anything, audit what is already present and only install what is missing. Follow these steps in order.

## Step 1: Pre-Flight Check (Detect Existing Installation)

Build a checklist of what is already installed before doing any installation work. Run each check and record the result. Skip any install step in Steps 3-7 whose check below already passes.

```bash
# Required tools — record version for each, or "missing"
command -v python3   && python3 --version
command -v git       && git --version
command -v uv        && uv --version
command -v dr        && dr --version
command -v pulumi    && pulumi version
command -v task      && task --version
command -v node      && node --version
command -v pip       && pip --version

# DataRobot CLI plugins (only meaningful if `dr` exists)
dr plugin list 2>/dev/null | grep -i assist

# Python SDK (in the user's active environment)
python3 -c "import datarobot; print(datarobot.__version__)" 2>/dev/null
python3 -c "import datarobot_predict; print('datarobot-predict installed')" 2>/dev/null

# Credential state
echo "DATAROBOT_API_TOKEN: ${DATAROBOT_API_TOKEN:+set (via env)}"
echo "DATAROBOT_ENDPOINT:  ${DATAROBOT_ENDPOINT:-not set}"
test -f ~/.config/datarobot/drconfig.yaml && echo "drconfig: found" || echo "drconfig: missing"

# If drconfig exists, verify credentials are actually valid
if test -f ~/.config/datarobot/drconfig.yaml; then
  dr auth check 2>/dev/null && echo "auth: valid" || echo "auth: INVALID (re-authentication required)"
fi
```

Compare each detected version to the minimums in the table in Step 3. Tell the user:
- What is already installed and at acceptable versions (skip)
- What is missing or below minimum version (install)
- Whether dr-cli is already authenticated (skip Step 6 if so, but confirm with user)

Only proceed past this step after presenting the diff to the user so they can confirm.

## Step 2: Detect Operating System

Detect the OS and tailor commands accordingly.

### Windows Users: WSL Required

**IMPORTANT**: DataRobot Agent Assist does NOT support native Windows. You MUST use WSL (Windows Subsystem for Linux).

#### Check if Running in WSL

```bash
uname -r | grep -i microsoft         # Returns output if in WSL
cat /proc/version | grep -i microsoft # Alternative
echo $WSL_DISTRO_NAME                 # Empty if not in WSL
```

#### If NOT in WSL

1. **Install WSL 2** (Windows 10/11). Open PowerShell as Administrator and run `wsl --install`, then restart when prompted. Default Ubuntu will be installed.
2. **Alternative manual install**: `wsl --install -d Ubuntu-22.04` from elevated PowerShell.
3. **Set up Ubuntu**: launch Ubuntu from the Start menu, create a username and password, then run `sudo apt update && sudo apt upgrade -y`.
4. **Return here**: once in WSL, re-run this skill from the Ubuntu terminal.

#### Supported Environments

- macOS — Homebrew install path
- Linux — distribution-specific installers
- WSL — Linux installers
- Native Windows — NOT supported; use WSL

## Step 3: Install Missing Core Dependencies

Only install the tools flagged as missing in Step 1.

| Tool | Minimum Version | Purpose |
|------|-----------------|---------|
| Python | 3.10+ | DataRobot SDK and Agent Assist |
| git | 2.30.0+ | Version control |
| uv | 0.9.0+ | Python package manager |
| dr-cli | 0.2.50+ | DataRobot CLI |
| Pulumi | 3.163.0+ | Infrastructure as Code |
| go-task | 3.43.3+ | Task runner |
| Node.js | 24+ | JavaScript runtime |

### macOS (Homebrew)

```bash
brew install datarobot-oss/taps/dr-cli uv pulumi/tap/pulumi go-task node git python
```

### Linux / WSL

Use the architecture-aware official installers below. These work on both x86_64 and ARM64.

- **dr-cli** (universal installer — auto-detects architecture):
  ```bash
  curl -fsSL https://cli.datarobot.com/install | sh
  ```

- **Python 3.10+** (uses whatever Python the distro ships; on Ubuntu 22.04 that's 3.10, on 24.04 it's 3.12 — both satisfy the minimum):
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-pip python3-venv
  ```

- **git**:
  ```bash
  sudo apt install -y git
  ```

- **uv** (Python package manager):
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **Node.js 24** (via nvm):
  ```bash
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
  source ~/.bashrc   # or ~/.zshrc
  nvm install 24
  nvm use 24
  ```

- **Pulumi**:
  ```bash
  curl -fsSL https://get.pulumi.com | sh
  ```

- **go-task**:
  ```bash
  sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin
  ```

Note: All Linux commands above also work in WSL.

## Step 4: Install Python SDK (in a virtual environment)

Modern Linux distributions enforce PEP 668 and reject `pip install` into the system Python. Always install the SDK into a `uv`-managed virtual environment so this works on Ubuntu 23.04+, 24.04, and macOS with Homebrew Python.

```bash
# Create and activate a project-scoped venv with uv
uv venv .venv
source .venv/bin/activate

# Install the SDK and prediction client into the venv
uv pip install datarobot datarobot-predict
```

If the user prefers `pip` directly, the same pattern applies — they must create and activate a venv first, then run `pip install datarobot datarobot-predict` inside it. Never instruct the user to run `pip install --break-system-packages` against the system Python.

## Step 5: Get API Key

If the user does not already have a DataRobot Personal API key:

1. Open: https://app.datarobot.com/account/developer-tools
2. Use the **Personal API keys** tab (NOT Application or Agent keys).
3. Wait for the user to provide the key.

## Step 6: Authenticate with dr-cli

If Step 1 showed `~/.config/datarobot/drconfig.yaml` already exists, ask the user if they want to re-authenticate or keep the existing credentials. Otherwise run:

```bash
dr auth login
```

This persists credentials in `~/.config/datarobot/drconfig.yaml`.

Optionally, offer to add these to the user's shell rc file (~/.zshrc, ~/.bashrc) for SDK use:

```bash
export DATAROBOT_ENDPOINT="<endpoint-url>"
export DATAROBOT_API_TOKEN="<api-token>"
```

## Step 7: Install Agent Assist Plugin

Skip if Step 1 showed the `assist` plugin already installed. Otherwise:

```bash
dr plugin install assist
```

## Step 8: Verify Installation

1. **CLI and plugins**:
   ```bash
   dr --version
   dr plugin list 2>/dev/null | grep -i assist
   ```

2. **Python SDK**:
   ```bash
   source .venv/bin/activate && python -c "import datarobot; datarobot.Client(connect_timeout=10); [print(p.project_name) for p in datarobot.Project.list(limit=3)]"
   ```
   if this fails due to the source command not working, try it without activating the venv

## Step 9: Print Summary

Summarize:
- Tools installed this session vs. tools already present
- Versions of every tool now on the path
- Config file locations:
  - `~/.config/datarobot/drconfig.yaml` (dr-cli)
  - Shell rc file (if env vars were added)
  - Project venv path (e.g. `./.venv`)
- Reminder: "Installation complete. Do not run `dr assist` yet unless in a dedicated empty directory."

## Important Notes

- **Do NOT run `dr assist`** during this setup. Only install and verify.
- Agent Assist must only be run from a dedicated empty directory to avoid overwriting existing files.
- Ensure all minimum version requirements are met before completing.
- If any verification step fails, troubleshoot before proceeding.
