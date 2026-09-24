# Serving a web UI (and its backend) through the workload endpoint

Applies when a workload **exposes a port serving a browser-facing web app** —
UI plus its own backend/API/WebSocket — reached via `dr workload endpoint
<id>`. Framework-agnostic (Jupyter, Streamlit, Gradio, SPA + REST/gRPC-web
backend, Shiny, plain Flask/Express). NOT needed for headless
machine-to-machine services.

## How the DataRobot edge gateway serves the endpoint

`dr workload endpoint <id>` returns a URL under a **path prefix**, e.g.

```
https://app.datarobot.com/api/v2/endpoints/workloads/<id>/
```

Four edge-gateway behaviors drive everything below. Verify for your cluster;
held on MTSaaS as of writing:

1. **Prefix STRIPPED inbound.** Browser requests `…/workloads/<id>/lab`;
   container receives `/lab`. Confirm via `dr workload logs` — app logs the
   *stripped* path.
2. **Gateway authenticates access.** DataRobot login required to reach the
   endpoint at all; unauthenticated requests get the platform's own
   challenge (a browser Basic-auth "Sign in" modal if the session is
   missing/expired). Edge is the auth gate.
3. **`Authorization` header consumed by the platform.** Endpoint lives under
   `/api/v2/`, so the edge treats inbound `Authorization` as a *DataRobot*
   API key. An app sending `Authorization: Bearer …`/`token …` to its own
   backend gets `401 {"message": "Invalid API key"}` **from the edge —
   request never reaches the container** (won't appear in `dr workload
   logs`).
4. **Responses NOT rewritten.** Edge doesn't re-add the prefix to redirect
   `Location`, HTML, or asset URLs. App output is what the browser gets —
   derive the prefix from `WORKLOAD_ID` (shim below) rather than relying on
   outbound rewriting.

**WebSockets supported** — `wss://…/workloads/<id>/…` upgrades pass through.
Real-time UIs work; no special handling beyond the sub-path rules below.

## The identity headers the edge forwards

Observed on an authenticated endpoint request (verify for your cluster — not
yet in public docs or the OpenAPI spec):

| Header | Content |
|---|---|
| `X-Datarobot-Username` | Caller's username |
| `X-User-Email` | Caller's email |
| `X-Datarobot-User-Id` | Caller's user id |
| `X-Datarobot-Org-Id` | Caller's org id |
| `X-Datarobot-Tenant-Id` | Caller's tenant id |
| `X-Datarobot-Consumer-Type` | `user` for interactive callers |
| `X-Datarobot-Identity-Token` | HMAC-signed identity token |
| `X-Forwarded-Prefix` | Exact workload endpoint path — observed correctly populated, matched `dr workload endpoint <id>`. Still prefer deriving from `WORKLOAD_ID` (below, platform-documented); treat this header as secondary confirmation until documented. |
| `traceparent` / B3 headers | W3C / B3 distributed-tracing context |

**Spoof test (do this before trusting any header for authorization):** forged
`X-Datarobot-Username`, `X-User-Email`, `X-Datarobot-User-Id`,
`X-Forwarded-Prefix` were all overwritten by the edge with real values — safe
to trust on this cluster. A forged `X-Datarobot-Identity-Token` was **not**
overwritten. **Don't trust `X-Datarobot-Identity-Token` unless the app
verifies its HMAC signature; no public verification key/endpoint found at
time of writing.** If unverified, ignore it and rely on the other
edge-overwritten headers.

Richer than the classic Custom Applications proxy, which only forwards a raw
visitor API key the app must resolve itself. On Workloads, an app reads
identity straight from these headers and applies its own
allowlist/authorization — no per-visitor key resolution call.

## The four things a web app must do

### 1. Be prefix-aware — the "prefix shim"

The non-obvious one — understand the shape before writing code.

**The bind.** Every URL the app emits — asset tags, API/XHR calls, WebSocket
URL, redirect `Location`s — must carry the prefix, or the browser resolves
against origin root and escapes the workload (→ 404, or a redirect to
DataRobot app login). But the edge delivers requests **stripped** and
doesn't rewrite responses. Two contradictory needs:

- **emit** URLs *with* the prefix (browser stays in the workload), yet
- **match** inbound requests arriving *without* it.

A thin **prefix shim** reconciles both: tell the app its external mount
point is the prefix (fixes outbound); route on the stripped path actually
received (fixes inbound).

**Derive the prefix from `WORKLOAD_ID` — don't pass it in.** Endpoint path
is always `/api/v2/endpoints/workloads/<workload-id>`; DataRobot
**auto-injects `WORKLOAD_ID`** into every container. Build the prefix at
startup — no extra env var, stays correct across rebuilds/replacements
(workload ID never changes):

```python
import os

PREFIX = f"/api/v2/endpoints/workloads/{os.environ['WORKLOAD_ID']}"  # no trailing slash
```

(Same path `dr workload endpoint <id>` prints, minus scheme/host — no fetch
or hardcode needed.)

> **Caveat — proton-id URL paths need an explicit override.** The
> `WORKLOAD_ID`-derived prefix only matches the workload-id endpoint
> (`/api/v2/endpoints/workloads/<workload-id>/`). The workload is also
> addressable by a **proton-id** path (`/protons/<proton-id>/…` — internal
> routing/health probes), with a different prefix that changes on every
> replacement (each roll = new proton). Proton ID isn't injected into the
> env, so it can't be derived like `WORKLOAD_ID`. To serve under the
> proton-id path, set the base-path **explicitly** via your own env var
> (e.g. `WORKLOAD_BASE_PATH`) and update it on every proton change. For the
> normal workload-id endpoint, `WORKLOAD_ID` derivation is all you need.

**Preferred: use the framework's mount setting (no custom code).** Most
WSGI/ASGI apps already implement this via `SCRIPT_NAME`/`root_path`:

```python
# WSGI (Flask/Django/Bottle/...). The edge already stripped the prefix, so
# PATH_INFO is the in-mount path; SCRIPT_NAME tells the app its external mount,
# and the framework prepends it to url_for()/redirect()/static URLs.
def prefix_shim(app):
    def wrapped(environ, start_response):
        environ["SCRIPT_NAME"] = PREFIX  # outbound URLs + redirects now carry PREFIX
        return app(
            environ, start_response
        )  # route on PATH_INFO (already stripped) = matches

    return wrapped


application = prefix_shim(application)
```

- **ASGI** (FastAPI/Starlette): same idea built in — run `uvicorn
  --root-path "/api/v2/endpoints/workloads/$WORKLOAD_ID"` (or set
  `root_path` on the app from the env var). Starlette prepends `root_path`
  to `url_for`/redirects and routes on the received path.
- **Streamlit / Shiny / SPA**: use the base-path option
  (`--server.baseUrlPath`, `server.rootUrl`, `<base href>`), no middleware.

**Fallback: frameworks coupling routing to base-path (Tornado/Jupyter).**
Setting base-path makes the server expect the prefix *in the request path*,
so stripped inbound requests 404. Set base-path to the prefix (outbound)
**and** re-add the prefix to inbound requests before routing:

```python
# Tornado/Jupyter: base_url is set to PREFIX (outbound). This shim re-adds the
# stripped prefix to the inbound path so base_url-mounted handlers match.
# Idempotent: a request that already carries the prefix (e.g. an in-cluster
# probe hitting the prefixed path) passes untouched.
_orig = Application.find_handler


def find_handler(self, request, **kw):
    p = request.path or "/"
    if p != PREFIX and not p.startswith(PREFIX + "/"):
        request.path = PREFIX + p
        request.uri = request.path + (f"?{request.query}" if request.query else "")
    return _orig(self, request, **kw)


Application.find_handler = find_handler
```

A reverse proxy baked into the image (nginx `sub_filter`/rewrite, Traefik
`StripPrefix`/`AddPrefix`) can play the same role. The shim also lets
**health probes** hit the bare or prefixed path (#4).

**Redirects.** With the mount configured, framework redirects already
include the prefix. The trap: app code with hardcoded *root-relative*
redirects/links (`redirect("/home")`, `href="/x"`) bypasses the mount,
escapes the prefix. Fix via the framework's URL builder/relative links, or
rewrite stray outbound `Location`s as a last resort:

```python
# Prepend PREFIX to any root-relative Location the app emits (WSGI).
# Guarded so links the framework already prefixed aren't doubled.
def fix_location(app):
    def wrapped(environ, start_response):
        def sr(status, headers, exc=None):
            headers = [
                (
                    k,
                    PREFIX + v
                    if k.lower() == "location"
                    and v.startswith("/")
                    and v != PREFIX
                    and not v.startswith(PREFIX + "/")
                    else v,
                )
                for k, v in headers
            ]
            return start_response(status, headers, exc)

        return app(environ, sr)

    return wrapped
```

### 2. Disable the app's built-in auth — let the edge be the gate

Edge already requires DataRobot login to reach the endpoint (#2). The app's
own token/password/cookie auth on top is redundant AND actively breaks
here:

- a bearer token the frontend sends is hijacked by the edge (#3);
- the app's login **cookies often don't round-trip** through the gateway —
  session never sticks (login POST redirects, then every page bounces back
  to login).

Configure the app to **trust the proxy / allow unauthenticated access**,
relying on the DataRobot edge for auth: turn off token auth (no bearer
header sent), turn off password/login, enable anonymous access. Examples:
Jupyter `ServerApp.token=""` + `allow_unauthenticated_access=True`;
Streamlit has no auth by default (fine); FastAPI/Express should skip its
auth middleware on this deployment.

> **Security — confirm the gate before disabling app auth; it's the app
> owner's call, not the agent's to make unilaterally.** Disable the app's
> auth only after confirming the endpoint genuinely requires DataRobot
> login (open the URL in a private window, no session — you should be
> blocked). Confirmed: access is gated by DataRobot login + RBAC. NOT
> confirmed (publicly reachable): keep the app's auth, solve #3/#4 another
> way (e.g. cookie-only auth, unique cookie names, no `Authorization`
> header). Never leave a code-executing app both reachable and
> unauthenticated. Even when confirmed, surface the tradeoff to the user
> first — disabling in-app auth is a security-relevant change (also drops
> per-visitor auth if the app is reached another way); the owner may prefer
> defense in depth.

### 3. Neutralize shared-origin cookie/CSRF collisions

App shares origin with the DataRobot app (e.g. `app.datarobot.com`), which
sets its own cookies (commonly `_xsrf`, session cookies). A same-named app
cookie collides — server may read the platform's value, fail its CSRF check
(e.g. Jupyter's `403 "XSRF cookie does not match POST argument"`).

- Prefer **disabling the app's CSRF check** once app auth is disabled and
  access is edge-gated (no app session to forge).
- Renaming the CSRF cookie is often NOT viable: compiled frontends often
  hard-code the name (e.g. JupyterLab reads `_xsrf` for its `X-XSRFToken`
  header) — a rename blinds the frontend, every API call fails the check.
  Test before relying on a rename.

### 4. Probe a path that exists WITHOUT auth

Health probes hit the container directly (not through the edge). Once app
auth is disabled, login routes may disappear (`/login` → 404) — a probe
pointed there fails, workload never goes ready. Point
`readinessProbe`/`livenessProbe` at a lightweight, always-available
endpoint (dedicated `/healthz`, or the app's status route). With the
inbound shim, an unprefixed probe path works — the shim re-adds the prefix.

## Diagnostic playbook (symptom → cause → fix)

Cross-check `dr workload logs <id>`: **failing request absent from pod logs
→ edge rejected it before the container** (edge/auth problem, #2/#3);
present with a status code → app problem (sub-path/CSRF).

| Symptom in the browser | Root cause | Fix |
|---|---|---|
| After login you land on the DataRobot app login, URL `…?next=%2F` | App emitted a root-relative redirect (`Location: /`) that escaped the prefix | Set base-path to the prefix + inbound shim (#1) |
| UI shell loads but assets/API 404; pod otherwise healthy | Proxy strips prefix; app base-path is `/` so generated URLs miss the prefix | #1 (base-path + shim) |
| `401 {"message":"Invalid API key"}` on API/XHR; those requests **absent** from pod logs | Edge hijacked the app's `Authorization` header (#3) | Disable app token auth so no bearer header is sent (#2) |
| Login "succeeds" (302) but every page bounces back to login | App login cookie not round-tripping through the edge | Disable app auth, trust the edge (#2) |
| Browser-native username/password "Sign in" modal | Edge Basic challenge — no DataRobot session in the browser | Log into DataRobot first; the edge, not the app, is prompting |
| `403 "XSRF cookie does not match"` on POST/login | `_xsrf` (or other) cookie collides with the DataRobot app's on the shared origin | Disable app CSRF check (#3) |
| Workload never leaves `launching`; probe 404/401 on a login path | Probe points at a route that no longer exists (auth disabled) or is edge-gated | Point probes at an unauthenticated app path (#4) |

## Minimal checklist for "serve my web app through the endpoint"

1. Build the prefix at startup from the auto-injected `WORKLOAD_ID`:
   `/api/v2/endpoints/workloads/$WORKLOAD_ID` (no extra env var to pass).
2. Set the app's base-path/root-path to that prefix; add an inbound
   prefix-restoring shim (or a reverse-proxy rewrite) if the framework
   couples inbound routing to the base-path.
3. Disable the app's own auth, enable anonymous access — after confirming
   the endpoint requires DataRobot login.
4. Disable the app's CSRF check (or verify a cookie rename doesn't break
   the frontend).
5. Point liveness/readiness probes at an unauthenticated path.
6. Verify end to end: open the endpoint while logged into DataRobot; UI
   loads under the prefix, API calls return 2xx (visible in `dr workload
   logs`), and any WebSocket connects.
