## DataRobot CLI Setup

The DataRobot CLI (`dr`) is required for managing DataRobot custom applications. Follow during the [Pre-requisite Check](../SKILL.md#pre-requisite-check).

### Verify Installation

Check if the CLI is installed:

```bash
dr --version
```

Expected output: `DataRobot CLI version: v0.2.66` (or similar)

### Install DataRobot CLI

If not installed, show the user the command for their platform and get their confirmation before running it. Never substitute a different URL.

**macOS:**
```bash
brew install datarobot-oss/taps/dr-cli
```

**Linux / WSL:**
```bash
curl -fsSL https://cli.datarobot.com/install | sh
```

**Windows:** native Windows is not supported. Use WSL and the Linux command.

### Upgrade CLI

If the CLI version is too old, run to upgrade:

```bash
dr self update --force
```

### Check Authentication Status

Verify the CLI is authenticated:

```bash
dr auth check
```

### Authenticate

If not authenticated, run:

```bash
dr auth login
```

This will guide the user through the authentication process interactively.
