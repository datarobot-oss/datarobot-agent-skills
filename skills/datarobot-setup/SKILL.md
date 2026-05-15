---
name: datarobot-setup
description: Sets up DataRobot for local development including Python SDK, dr-cli, Agent Assist, and all required dependencies
---

# DataRobot Local Development Setup

You are helping set up DataRobot for local development. Follow these steps exactly:

## Step 1: Detect Operating System

Detect the operating system and tailor installation commands accordingly.

### Windows Users: WSL Required

**IMPORTANT**: DataRobot Agent Assist does NOT support native Windows. You MUST use WSL (Windows Subsystem for Linux).

#### Check if Running in WSL

Run one of these commands to detect WSL:
```bash
uname -r | grep -i microsoft  # Returns output if in WSL
cat /proc/version | grep -i microsoft  # Alternative check
```

Or check for the `WSL_DISTRO_NAME` environment variable:
```bash
echo $WSL_DISTRO_NAME
```

#### If NOT in WSL

If the user is on Windows but not in WSL, provide these instructions:

1. **Install WSL 2** (Windows 10/11):
   - Open PowerShell as Administrator
   - Run: `wsl --install`
   - Restart computer when prompted
   - Default Ubuntu distribution will be installed

2. **Alternative manual installation**:
   - Open PowerShell as Administrator:
     ```powershell
     wsl --install -d Ubuntu-22.04
     ```

3. **Set up Ubuntu**:
   - Launch "Ubuntu" from Start menu
   - Create username and password
   - Update packages: `sudo apt update && sudo apt upgrade -y`

4. **Return to this setup**: Once in WSL, run the DataRobot setup again from within the Ubuntu terminal.

#### Supported Environments

- ✅ **macOS** - Use Homebrew installation
- ✅ **Linux** - Use distribution-specific installers
- ✅ **WSL (Windows Subsystem for Linux)** - Use Linux installers
- ❌ **Native Windows** - NOT supported, must use WSL

## Step 2: Install Core Dependencies

Install the following tools at minimum versions:

| Tool | Minimum Version | Purpose |
|------|-----------------|---------|
| Python | 3.10+ | Required for DataRobot SDK and Agent Assist |
| git | 2.30.0+ | Version control |
| uv | 0.9.0+ | Python package manager |
| dr-cli | 0.2.50+ | DataRobot CLI |
| Pulumi | 3.163.0+ | Infrastructure as Code |
| go-task | 3.43.3+ | Task runner |
| Node.js | 24+ | JavaScript runtime |

### macOS Installation (Homebrew)

```bash
brew install datarobot-oss/taps/dr-cli uv pulumi/tap/pulumi go-task node git python
```

### Linux / WSL Installation

For Linux or WSL, install each tool from official sources:

- **dr-cli**:
  ```bash
  curl -LO https://github.com/datarobot-oss/cli/releases/latest/download/dr-linux-amd64
  chmod +x dr-linux-amd64
  sudo mv dr-linux-amd64 /usr/local/bin/dr
  ```

- **Python 3.10+**:
  ```bash
  sudo apt update
  sudo apt install python3.10 python3-pip python3.10-venv -y
  ```

- **git**:
  ```bash
  sudo apt install git -y
  ```

- **uv** (Python package manager):
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **Node.js 24** (using nvm):
  ```bash
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
  source ~/.bashrc  # or ~/.zshrc
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

**Note for WSL**: All commands above work identically in WSL as they do in native Linux.

## Step 3: Install Python SDK

```bash
pip install datarobot datarobot-predict
```

## Step 4: Get API Key

Ask the user for their DataRobot Personal API key. If they don't have one:

1. Tell them to open: https://app.datarobot.com/account/developer-tools
2. Instruct them to use the "Personal API keys" tab (NOT Application or Agent keys)
3. Wait for them to provide the key

## Step 5: Authenticate with dr-cli

Run `dr auth login` to:
- Persist credentials in `~/.config/datarobot/drconfig.yaml`
- Set up authentication for CLI operations

Ask the user if they want shell persistence. If yes, add these to their shell rc file (~/.zshrc, ~/.bashrc, etc.):

```bash
export DATAROBOT_ENDPOINT="<endpoint-url>"
export DATAROBOT_API_TOKEN="<api-token>"
```

## Step 6: Install Agent Assist Plugin

```bash
dr plugin install assist
```

## Step 7: Verify Installation

Run the following verification steps:

1. **Check CLI version and plugins**:
   ```bash
   dr --version
   dr plugin list
   dr assist --help
   ```

2. **Test Python SDK** by running this snippet:
   ```python
   import datarobot as dr
   dr.Client()
   for p in dr.Project.list()[:3]:
       print(p.project_name)
   ```

## Step 8: Print Summary

Print a summary including:
- All tools installed with their versions
- Configuration file locations:
  - `~/.config/datarobot/drconfig.yaml` (dr-cli config)
  - Shell rc file (if environment variables were added)
- Next steps reminder: "Installation complete. Do not run `dr assist` yet unless in a dedicated empty directory."

## Important Notes

- **Do NOT run `dr assist`** during this setup - only install and verify
- Agent Assist must only be run from a dedicated empty directory to avoid overwriting existing files
- Ensure all minimum version requirements are met
- If any verification step fails, troubleshoot before proceeding
