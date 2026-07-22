#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Frictionless trial signup + CLI authentication for datarobot-setup Step 5.

This helper collapses the brand-new-user onboarding path into a few CLI-driven
steps so the developer never has to hunt for the trial form, copy an API key,
or leave the terminal for longer than a single browser round-trip.

Why it is split into subcommands (not one blocking script):
    The datarobot-setup skill is driven by a coding agent that gates on the
    *user's* chat replies, not on a script's stdin. So the agent calls these
    subcommands in sequence and does the "wait for the human" part itself.

    check        -> Is the machine already authenticated? (detection / skip)
    signup       -> Open the browser to trial signup (email pre-filled). Returns
                    immediately; the agent then waits for the user to finish.
    login        -> Run `dr auth login`; the already-authenticated browser
                    session makes this a one-click authorize, and the API key is
                    captured into drconfig.yaml automatically (no copy-paste).
    all          -> Interactive convenience: check -> signup -> (Enter gate) ->
                    login. Only prompts when run in a real TTY.

How the key actually lands (verified against datarobot-oss/cli
internal/auth/auth.go): `dr auth login` opens
`{host}/account/developer-tools?cliRedirect=true`, spins up a local server on
localhost:51164, and the developer-tools page 302-redirects the browser to
`http://localhost:51164/?key=<APIKEY>`. It rides the browser's existing app
session, so signing up first (this script's `signup` step) makes the `login`
step hands-free.

Usage:
    python signup_and_authenticate.py check   [--host URL] [--json]
    python signup_and_authenticate.py signup  [--host URL] [--email you@co.com] [--mode app|deeplink]
    python signup_and_authenticate.py login   [--host URL]
    python signup_and_authenticate.py all     [--host URL] [--email you@co.com] [--mode app|deeplink]

Exit codes:
    0  success (authenticated, or step completed)
    2  `check`: not authenticated yet (normal for a new user)
    1  hard error (e.g. `dr` not installed, login failed)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser

DEFAULT_HOST = "https://app.datarobot.com"

# --- Auth0 signup deep-link (US cloud) -------------------------------------
# Values captured from a live trial signup HAR. These are specific to the
# US-cloud public app; EU/JP or self-managed installs use a different Auth0
# tenant and client, so deep-link mode is only attempted when --host is US cloud.
#
# STATUS (from live testing 2026-07):
#   ✓ A self-initiated /authorize with client_id + screen_hint/initial_display
#     DOES render the lean DataRobot signup page (confirmed live).
#   ✓ EMAIL signup completes end-to-end. On email submit the app creates an
#     account-invite and emails a link back to
#     app.datarobot.com/account/oidc/redirect?alsInviteId=… — which is
#     APP-initiated (app-generated state/nonce). So the original self-initiated
#     `state` is moot for this path; no callback state wall.
#   ? SOCIAL signup (Google/GitHub) via deep-link returns straight to our
#     self-initiated /account/oidc/callback (no invite re-init), so callback
#     `state` acceptance is UNVERIFIED. If it fails, use --mode app for social.
#   ✗ Cold-screen email pre-fill is NOT possible via URL param. The email box is
#     only pre-filled from a server-side invite record (ALS: /api/account-invite
#     /<id>), which exists only after email submit. `autofill_email`/`login_hint`
#     /`email` do nothing on the initial trial-signup screen.
#   ✗ `/account/oidc/redirect` strictly allow-lists params and rejects display
#     hints, so the app itself cannot be asked to show signup.
US_AUTH_DOMAIN = "https://login.datarobot.com"
US_CLIENT_ID = "xRJctzk4frlytI32DsAYHs0dhd7FQBli"


def run(cmd: list[str], timeout: int | None = None, capture: bool = True):
    """Run a command; return (returncode, stdout, stderr). Never raises on rc."""
    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or ""), (proc.stderr or "")
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s: {' '.join(cmd)}"


def dr_installed() -> bool:
    return shutil.which("dr") is not None


def is_authenticated(host: str) -> bool:
    """True if `dr auth check` passes. Short timeout; never prompts."""
    if not dr_installed():
        return False
    rc, _, _ = run(["dr", "auth", "check"], timeout=35)
    return rc == 0


def git_email() -> str:
    rc, out, _ = run(["git", "config", "--get", "user.email"], timeout=10)
    return out.strip() if rc == 0 else ""


def is_us_cloud(host: str) -> bool:
    return host.rstrip("/") in (DEFAULT_HOST, "https://app.datarobot.com")


def build_signup_url(host: str, email: str, mode: str) -> tuple[str, str]:
    """Return (url, mode_used). Falls back to app-initiated when deep-link
    cannot be built safely for the given host."""
    host = host.rstrip("/")

    if mode == "deeplink":
        if not is_us_cloud(host):
            # No known Auth0 tenant/client for non-US hosts; stay robust.
            return f"{host}/account/oidc/redirect", "app"
        params = {
            # Auth0 /authorize requires `client_id` (NOT `client`, which is the
            # classic hosted-login page param). Getting this wrong yields
            # "invalid_request: Missing required parameter: client_id".
            "client_id": US_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": f"{host}/account/oidc/callback",
            "scope": "openid email profile",
            # Ask Auth0 to render signup. `screen_hint` is the New Universal
            # Login key; `initial_display` is the classic Lock key. Send both;
            # Auth0 ignores unknown /authorize params (unlike the app's redirect).
            "screen_hint": "signup",
            "initial_display": "signup",
        }
        if email:
            # Best-effort email hint. NOTE: live testing showed the *cold*
            # trial-signup screen does NOT pre-fill from any URL param — the page
            # only auto-fills email from a server-side invite record (ALS), which
            # exists only after the user submits their email. `autofill_email` is
            # read solely by the invite/link-target components, so this is a
            # harmless no-op on the initial screen. Kept in case an invite context
            # applies; drop it if you prefer a cleaner URL.
            params["autofill_email"] = email
        query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        return f"{US_AUTH_DOMAIN}/authorize?{query}", "deeplink"

    # mode == "app" (robust default): the app initiates OIDC and sets state.
    # The Auth0 page still offers a "Sign up" toggle + Google/GitHub buttons.
    return f"{host}/account/oidc/redirect", "app"


def _is_wsl() -> bool:
    if not hasattr(os, "uname"):
        return False
    return "microsoft" in os.uname().release.lower()


def open_browser(url: str) -> bool:
    """Best-effort cross-platform open. Always returns whether a browser was
    launched; the caller prints the URL regardless so nothing is lost."""
    # WSL: webbrowser usually can't reach the Windows browser. Try explorer.
    if _is_wsl():
        for opener in ("wslview", "explorer.exe"):
            if shutil.which(opener):
                rc, _, _ = run([opener, url], timeout=10)
                if rc == 0:
                    return True
    try:
        return webbrowser.open(url, new=2)
    except Exception:
        return False


def print_signup_guidance(url: str, opened: bool, mode: str) -> None:
    print()
    print("🚀 Start your DataRobot free trial (30 days, no credit card):")
    print()
    print(f"    {url}")
    print()
    if not opened:
        print("   (Your browser didn't open automatically — copy the link above.)")
        print()
    print("   ▶ Fastest path: sign up with GitHub or Google — this skips the")
    print("     email-verification step entirely and gets you straight in.")
    print("   ▶ Otherwise: enter your email, click the verification link we send,")
    print("     then set a password.")
    print()
    print("   Finish until you land on the DataRobot welcome screen, then come")
    print(
        "   back here — the CLI will grab your API key automatically (no copy-paste)."
    )
    if mode == "deeplink":
        print()
        print("   NOTE: deep-link mode is experimental; if signup errors at the")
        print("   callback, re-run with `--mode app`.")
    print()


def cmd_check(args) -> int:
    installed = dr_installed()
    authed = is_authenticated(args.host) if installed else False
    if args.json:
        print(
            json.dumps(
                {
                    "dr_installed": installed,
                    "authenticated": authed,
                    "host": args.host,
                }
            )
        )
    else:
        if not installed:
            print("dr CLI not found on PATH (complete the install steps first).")
        elif authed:
            print("✅ Already authenticated with DataRobot.")
        else:
            print("Not authenticated yet.")
    return 0 if authed else 2


def cmd_signup(args) -> int:
    email = args.email or git_email()
    url, mode_used = build_signup_url(args.host, email, args.mode)
    if getattr(args, "print_url", False):
        # Just emit the URL (for fast iteration / piping); don't open a browser.
        print(url)
        return 0
    opened = open_browser(url)
    print_signup_guidance(url, opened, mode_used)
    return 0


def cmd_login(args) -> int:
    if not dr_installed():
        print(
            "❌ dr CLI not found on PATH. Install it before authenticating.",
            file=sys.stderr,
        )
        return 1
    print("🔐 Connecting the CLI to your DataRobot account...")
    # Inherit stdio so the CLI's browser prompt / fallback URL is visible.
    # No timeout: this blocks on the browser callback (localhost:51164).
    rc, _, _ = run(["dr", "auth", "login", args.host], capture=False)
    if rc != 0:
        print(
            "❌ `dr auth login` did not complete. You can re-run this step.",
            file=sys.stderr,
        )
        return 1
    if is_authenticated(args.host):
        print("✅ Authenticated. API key stored in ~/.config/datarobot/drconfig.yaml")
        return 0
    print("⚠️  Login ran but verification failed. Try `dr auth check`.", file=sys.stderr)
    return 1


def cmd_all(args) -> int:
    if is_authenticated(args.host):
        print("✅ Already authenticated with DataRobot — nothing to do.")
        return 0
    cmd_signup(args)
    if sys.stdin.isatty():
        try:
            input("Press Enter once you've reached the DataRobot welcome screen... ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        return cmd_login(args)
    # Non-interactive (agent-driven): stop here; the agent runs `login` next
    # after the user confirms signup is done.
    print("Next: after finishing signup, run this script with `login`.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DataRobot trial signup + CLI auth helper."
    )
    parser.add_argument("action", choices=["check", "signup", "login", "all"])
    parser.add_argument(
        "--host",
        default=os.environ.get("DATAROBOT_ENDPOINT_HOST", DEFAULT_HOST),
        help=f"DataRobot app URL (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--email",
        default="",
        help="Email to pre-fill on signup (default: git config user.email).",
    )
    parser.add_argument(
        "--mode",
        choices=["app", "deeplink"],
        default="app",
        help="signup URL style: 'app' (robust, default) or 'deeplink' (pre-fills email; validate live).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Machine-readable output (check only)."
    )
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="signup only: print the URL instead of opening a browser.",
    )
    args = parser.parse_args()

    # Normalize a bare host into a URL.
    if not args.host.startswith(("http://", "https://")):
        args.host = "https://" + args.host

    return {
        "check": cmd_check,
        "signup": cmd_signup,
        "login": cmd_login,
        "all": cmd_all,
    }[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
