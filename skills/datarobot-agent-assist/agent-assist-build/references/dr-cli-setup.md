## DataRobot CLI Setup

The DataRobot CLI (`dr`) is required for managing DataRobot custom applications. Follow during the [Pre-requisite Check](../SKILL.md#pre-requisite-check).

### Install DataRobot CLI

If not installed, run:

**macOS/Linux:**
```bash
curl https://cli.datarobot.com/install | sh
```

**Windows:**
```powershell
irm https://cli.datarobot.com/winstall | iex
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
