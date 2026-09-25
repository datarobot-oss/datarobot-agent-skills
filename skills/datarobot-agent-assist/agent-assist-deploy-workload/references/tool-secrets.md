# Storing tool secrets as DataRobot credentials

Store each tool secret as a DataRobot credential yourself, once the user has put it in `.env` (see `app-contract.md`). This reads the one value and sends it without it ever showing up in the output:

```bash
eval "$(dr auth export)"
uv run --with python-dotenv --with httpx python - <<'PY'
import os, httpx
from dotenv import dotenv_values
name = "SOME_TOOL_API_KEY"
r = httpx.post(f"{os.environ['DATAROBOT_ENDPOINT']}/credentials/",
    headers={"Authorization": f"Bearer {os.environ['DATAROBOT_API_TOKEN']}"},
    json={"name": "<agent-name>-some-tool-api-key", "credentialType": "api_token",
          "apiToken": dotenv_values(".env")[name]})
print(r.status_code, r.json().get("credentialId") or r.json().get("id"))
PY
```

Put the id it prints into `drCredentialId`. A 409 means the name is taken, possibly by someone else's credential, so pick a new name rather than reusing it.
