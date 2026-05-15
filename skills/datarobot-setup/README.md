# DataRobot Setup Skill

A Claude Code skill that automates the complete setup of DataRobot for local development, including the Python SDK, dr-cli, Agent Assist, and all required dependencies.

## What This Skill Does

This skill guides you through the complete DataRobot development environment setup by:

1. Detecting your operating system (macOS, Linux, or WSL)
2. Installing all required dependencies at minimum supported versions
3. Setting up the DataRobot Python SDK
4. Configuring dr-cli authentication
5. Installing the Agent Assist plugin
6. Verifying the complete installation
7. Providing a summary of installed components

## Platform Support

| Platform | Support Status | Installation Method |
|----------|---------------|---------------------|
| macOS | ✅ Fully Supported | Homebrew |
| Linux | ✅ Fully Supported | Distribution-specific installers |
| WSL (Windows) | ✅ Fully Supported | Linux installers |
| Native Windows | ❌ NOT Supported | Must use WSL |

### Windows Users

DataRobot Agent Assist requires WSL (Windows Subsystem for Linux). This skill will:
- Detect if you're running in WSL
- Provide step-by-step WSL installation instructions if needed
- Guide you through Ubuntu setup
- Run the complete installation once in WSL environment

## Dependencies Installed

The skill installs the following tools at minimum required versions:

| Tool | Minimum Version | Purpose |
|------|-----------------|---------|
| Python | 3.10+ | Required for DataRobot SDK and Agent Assist |
| git | 2.30.0+ | Version control system |
| uv | 0.9.0+ | Python package manager |
| dr-cli | 0.2.50+ | DataRobot command-line interface |
| Pulumi | 3.163.0+ | Infrastructure as Code tool |
| go-task | 3.43.3+ | Task automation runner |
| Node.js | 24+ | JavaScript runtime environment |

Additionally installs:
- `datarobot` - DataRobot Python SDK
- `datarobot-predict` - DataRobot prediction client
- `assist` plugin for dr-cli

## Usage

Invoke the skill in Claude Code:

```
/datarobot-setup
```

Or if Claude detects you're setting up DataRobot, it may automatically suggest this skill.

## What to Expect

### During Setup

1. **OS Detection**: The skill detects your platform and tailors commands accordingly
2. **Dependency Installation**: Installs all required tools using platform-appropriate methods
3. **API Key Request**: Prompts you for your DataRobot Personal API key
4. **Authentication**: Runs `dr auth login` and optionally sets up shell environment variables
5. **Plugin Installation**: Installs the Agent Assist plugin
6. **Verification**: Tests all installations and prints version information
7. **Summary**: Provides a complete report of what was installed

### API Key Required

You'll need a DataRobot Personal API key. The skill will guide you to:
- https://app.datarobot.com/account/developer-tools
- Use the "Personal API keys" tab (NOT Application or Agent keys)

### Configuration Files Created

- `~/.config/datarobot/drconfig.yaml` - dr-cli credentials
- Shell rc file (optional) - `DATAROBOT_ENDPOINT` and `DATAROBOT_API_TOKEN` environment variables

## Important Notes

### Safety Features

- ⚠️ **Does NOT run `dr assist`** - Only installs and verifies
- ⚠️ **Dedicated directory warning** - Reminds you that `dr assist` must only be run from an empty directory
- ✅ **Version checking** - Ensures all minimum version requirements are met
- ✅ **Verification steps** - Tests Python SDK and CLI functionality before completing

### After Setup

Once setup is complete:
- All tools will be verified and working
- You'll have a summary of installed versions
- You'll be ready to use DataRobot APIs and tools
- Remember: Only run `dr assist` from a dedicated empty directory

## Troubleshooting

If the skill encounters issues:

1. **Version conflicts**: The skill checks minimum versions - upgrade if prompted
2. **API key issues**: Ensure you're using a Personal API key, not Application or Agent keys
3. **WSL detection**: Run `echo $WSL_DISTRO_NAME` to verify you're in WSL
4. **Permission errors**: Some installations may require `sudo` (Linux/WSL)

## References

This skill follows the official DataRobot documentation:
- [API Quickstart](https://docs.datarobot.com/en/docs/api/dev-learning/api-quickstart.html)
- [dr-cli Getting Started](https://docs.datarobot.com/en/docs/agentic-ai/cli/getting-started.html)
- [Agent Assist Installation](https://docs.datarobot.com/en/docs/agentic-ai/agent-assist/installation.html)

## Skill Location

This skill is installed at:
```
~/.claude/skills/datarobot-setup/SKILL.md
```

You can edit the skill file directly to customize the setup process for your needs.

## Version

Created: 2026-05-12
Last Updated: 2026-05-12
Compatible with: Claude Code (all versions with skill support)
