# Storing tool secrets as DataRobot credentials

Store each tool secret as a DataRobot credential yourself, once the user has put it in `.env` (see `app-contract.md`). This reads the one value and sends it without it ever showing up in the output. Pass the full path of the project's `.env`, because the shell's working directory often isn't `<target_dir>`:

```bash
eval "$(dr auth export)"
uv run --no-project --with python-dotenv --with httpx python - "<target_dir>/.env" <<'PY'
import os, sys, httpx
from dotenv import dotenv_values
name = "SOME_TOOL_API_KEY"
value = dotenv_values(sys.argv[1]).get(name)
if not value:
    sys.exit(f"{name} is empty or missing in {sys.argv[1]}")
r = httpx.post(f"{os.environ['DATAROBOT_ENDPOINT']}/credentials/",
    headers={"Authorization": f"Bearer {os.environ['DATAROBOT_API_TOKEN']}"},
    json={"name": "<agent-name>-some-tool-api-key", "credentialType": "api_token",
          "apiToken": value})
print(r.status_code, r.json().get("credentialId") or r.json().get("id"))
PY
```

If it exits with "empty or missing", the user hasn't saved the key yet. Repeat the `.env` instructions from `app-contract.md` and run it again. Put the id it prints into `drCredentialId`. A 409 means the name is taken, possibly by someone else's credential, so pick a new name rather than reusing it.
