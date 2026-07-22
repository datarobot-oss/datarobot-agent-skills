# Serving a web UI (and its backend) through the workload endpoint

Applies whenever a workload **exposes a port that serves a browser-facing web
app** — a UI plus its own backend/API/WebSocket — and users reach it through
`dr workload endpoint <id>`. This is framework-agnostic (Jupyter, Streamlit,
Gradio, a SPA + REST/gRPC-web backend, Shiny, a plain Flask/Express app, …).
It is NOT needed for headless services called machine-to-machine.

## How the DataRobot edge gateway serves the endpoint

`dr workload endpoint <id>` returns a URL under a **path prefix**, e.g.

```
https://app.datarobot.com/api/v2/endpoints/workloads/<id>/
```

Four behaviors of that edge gateway drive everything below. Verify them for the
target cluster, but they held on MTSaaS as of this writing:

1. **The prefix is STRIPPED inbound.** The browser requests
   `…/workloads/<id>/lab`; the container receives `/lab`. Confirm from
   `dr workload logs` — the app logs the *stripped* path.
2. **The gateway authenticates access.** A user must be logged into DataRobot
   to reach the endpoint at all; an unauthenticated request is met with the
   platform's own challenge (you may see a browser Basic-auth "Sign in" modal
   if the DataRobot session is missing/expired). The edge is the auth gate.
3. **The `Authorization` header is consumed by the platform.** Because the
   endpoint lives under `/api/v2/`, the edge treats an inbound `Authorization`
   header as a *DataRobot* API key. An app (or app frontend) that sends
   `Authorization: Bearer …`/`token …` to its own backend gets
   `401 {"message": "Invalid API key"}` **from the edge — the request never
   reaches the container** (it won't appear in `dr workload logs`).
4. **Responses are NOT rewritten.** The edge does not re-add the prefix to the
   app's redirect `Location` headers, HTML, or asset URLs; and it does not
   inject `X-Forwarded-Prefix` you can rely on. What the app emits is what the
   browser gets.

**WebSockets are supported** — `wss://…/workloads/<id>/…` upgrades pass through
to the container. Real-time UIs work; no special handling beyond the sub-path
rules below.

## The four things a web app must do

### 1. Be prefix-aware — the "prefix shim"

This is the non-obvious one; it cost the most time to figure out, so understand
the shape before writing code.

**The bind.** Every URL the app emits — asset tags, API/XHR calls, the
WebSocket URL, and HTTP redirect `Location`s — must carry the endpoint prefix,
or the browser resolves it against the origin root and it escapes the workload
(→ 404, or a redirect that lands on the DataRobot app login). But the edge
delivers requests with the prefix **stripped** and does **not** rewrite
responses. So the app has two seemingly contradictory needs:

- **emit** URLs *with* the prefix (so the browser stays inside the workload), yet
- **match** inbound requests that arrive *without* it.

A thin **prefix shim** reconciles the two: tell the app its external mount point
is the prefix (fixes outbound), and route on the stripped path the app actually
received (fixes inbound).

**Derive the prefix from `WORKLOAD_ID` — don't pass it in.** The endpoint path is
always `/api/v2/endpoints/workloads/<workload-id>`, and DataRobot **auto-injects
the managed env var `WORKLOAD_ID`** into every workload container. Build the
prefix from it at startup — no extra env var to plumb through, and it stays
correct across rebuilds/replacements (the workload ID never changes):

```python
import os
PREFIX = f"/api/v2/endpoints/workloads/{os.environ['WORKLOAD_ID']}"  # no trailing slash
```

(That's the same path `dr workload endpoint <id>` prints, minus scheme/host — no
need to fetch or hardcode it.)

> **Caveat — proton-id URL paths need an explicit override.** The
> `WORKLOAD_ID`-derived prefix only matches the workload-id endpoint
> (`/api/v2/endpoints/workloads/<workload-id>/`). The same workload is also
> addressable by a **proton-id** path (`/protons/<proton-id>/…` — e.g. how
> internal routing/health probes reach it), and that prefix is different *and*
> changes on every replacement (each roll creates a new proton). The proton ID
> is **not** injected into the container env, so it can't be derived at startup
> like `WORKLOAD_ID` is. If you actually need to serve under the proton-id path,
> set the base-path prefix **explicitly** via your own env var
> (e.g. `WORKLOAD_BASE_PATH`) instead of deriving it — and update it whenever the
> proton changes. For the normal browser-facing workload-id endpoint, the
> `WORKLOAD_ID` derivation above is all you need.

**Preferred: use the framework's mount setting (no custom code).** Most WSGI /
ASGI apps already implement exactly this via `SCRIPT_NAME` / `root_path`:

```python
# WSGI (Flask/Django/Bottle/...). The edge already stripped the prefix, so
# PATH_INFO is the in-mount path; SCRIPT_NAME tells the app its external mount,
# and the framework prepends it to url_for()/redirect()/static URLs.
def prefix_shim(app):
    def wrapped(environ, start_response):
        environ["SCRIPT_NAME"] = PREFIX          # outbound URLs + redirects now carry PREFIX
        return app(environ, start_response)      # route on PATH_INFO (already stripped) = matches
    return wrapped

application = prefix_shim(application)
```

- **ASGI** (FastAPI/Starlette): the same idea is built in — run
  `uvicorn --root-path "/api/v2/endpoints/workloads/$WORKLOAD_ID"` (or set
  `root_path` on the app from the env var). Starlette prepends `root_path` to
  `url_for`/redirects and routes on the received path.
- **Streamlit / Shiny / SPA**: use the base-path option
  (`--server.baseUrlPath`, `server.rootUrl`, `<base href>`), no middleware.

**Fallback: frameworks that couple routing to the base-path (Tornado / Jupyter).**
Here setting the base-path makes the server expect the prefix to be *present in
the request path*, so the stripped inbound requests 404. Set the base-path to
the prefix (for outbound) **and** re-add the prefix to the inbound request path
before routing:

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
        request.uri  = request.path + (f"?{request.query}" if request.query else "")
    return _orig(self, request, **kw)
Application.find_handler = find_handler
```

A reverse proxy baked into the image (nginx `sub_filter`/rewrite, Traefik
`StripPrefix`/`AddPrefix`) can play the same role. The shim also lets **health
probes** hit either the bare or prefixed path (see #4).

**Redirects specifically.** With the mount configured, framework-issued
redirects already include the prefix. The trap is app code that hardcodes
*root-relative* redirects or links (`redirect("/home")`, `href="/x"`): those
bypass the mount and escape the prefix. Fix them to use the framework's URL
builder / relative links, or rewrite stray outbound `Location`s as a last
resort:

```python
# Prepend PREFIX to any root-relative Location the app emits (WSGI).
# Guarded so links the framework already prefixed aren't doubled.
def fix_location(app):
    def wrapped(environ, start_response):
        def sr(status, headers, exc=None):
            headers = [
                (k, PREFIX + v if k.lower() == "location"
                       and v.startswith("/") and not v.startswith(PREFIX + "/") else v)
                for k, v in headers
            ]
            return start_response(status, headers, exc)
        return app(environ, sr)
    return wrapped
```

### 2. Disable the app's built-in auth — let the edge be the gate

The edge already requires a DataRobot login to reach the endpoint (behavior
#2). Running the app's own token/password/cookie auth on top is redundant AND
actively breaks here:

- a bearer token the frontend sends is hijacked by the edge (behavior #3);
- the app's own login **cookies often don't round-trip** through the gateway,
  so the session never sticks (login POST returns a redirect, then every page
  bounces back to the login screen).

So configure the app to **trust the proxy / allow unauthenticated access**, and
rely on the DataRobot edge for authentication. Concretely: turn off token auth
(so no bearer header is ever sent), turn off password/login, and enable
anonymous access. Framework examples: Jupyter
`ServerApp.token=""` + `allow_unauthenticated_access=True`; Streamlit has no
auth by default (fine); a FastAPI/Express app should skip its auth middleware
on this deployment.

> **Security — confirm the gate before disabling app auth.** Only disable the
> app's auth once you have confirmed the endpoint genuinely requires a
> DataRobot login (open the URL in a private window with no DataRobot session;
> you should be blocked). If confirmed, access is gated by the DataRobot login
> and RBAC on the workload. If NOT (endpoint publicly reachable), keeping the
> app's auth is required — but then you must solve behaviors #3/#4 another way
> (e.g. cookie-only auth with unique cookie names and no `Authorization`
> header). Never leave a code-executing app both reachable and unauthenticated.

### 3. Neutralize shared-origin cookie/CSRF collisions

The app is served from the same origin as the DataRobot app (e.g.
`app.datarobot.com`), which sets its own cookies (commonly `_xsrf`,
session cookies). A same-named cookie from the app collides — the server may
read the platform's value and fail its CSRF check (e.g. Jupyter's
`403 "XSRF cookie does not match POST argument"`).

- Prefer **disabling the app's CSRF check** when app auth is already disabled
  and access is edge-gated (there is no app session to forge).
- Renaming the app's CSRF cookie is often NOT viable: compiled frontends
  frequently hard-code the cookie name (e.g. JupyterLab reads `_xsrf` to build
  its `X-XSRFToken` header), so a rename blinds the frontend and every API call
  then fails the check. Test before relying on a rename.

### 4. Probe a path that exists WITHOUT auth

Health probes hit the container directly (not through the edge). Once app auth
is disabled, login routes may disappear (e.g. `/login` → 404), so a probe
pointed at them fails and the workload never goes ready. Point
`readinessProbe`/`livenessProbe` at a lightweight, always-available endpoint
(a dedicated `/healthz`, or the app's status route). With the inbound shim in
place, an unprefixed probe path works because the shim re-adds the prefix.

## Diagnostic playbook (symptom → cause → fix)

Always cross-check `dr workload logs <id>`: **if a failing request does NOT
appear in the pod logs, the edge rejected it before the container** (an
edge/auth problem — behaviors #2/#3); if it appears with a status code, it's an
app problem (sub-path/CSRF).

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
   prefix-restoring shim (or a reverse-proxy rewrite) if the framework couples
   inbound routing to the base-path.
3. Disable the app's own authentication and enable anonymous access — after
   confirming the endpoint requires a DataRobot login.
4. Disable the app's CSRF check (or verify a cookie rename doesn't break the
   frontend).
5. Point liveness/readiness probes at an unauthenticated path.
6. Verify end to end: open the endpoint while logged into DataRobot; the UI
   loads under the prefix, API calls return 2xx (visible in `dr workload logs`),
   and any WebSocket connects.
