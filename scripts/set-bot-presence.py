#!/usr/bin/env python3
"""
One-shot script that configures @BBBot's chat-side presence on Telegram:

- Menu button → "Open Workout Tracker" launching the Mini App at WEBAPP_URL.
- Short description (shown next to the bot name in search / chat list).
- Description (shown in the empty-chat splash before the user sends /start).
- Commands list cleared (we used to have /start, /history, etc.; not anymore).

We removed the polling bot, so this is how users get a useful "what's this bot
do?" experience without the bot ever needing to be online. Idempotent — set it
once or run on every service start; result is the same.

Reads BOT_TOKEN and WEBAPP_URL from the environment. Exits non-zero only on
network failures; per-call HTTP errors are logged but treated as warnings.
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

API_BASE = "https://api.telegram.org/bot{token}/{method}"

SECRETS_FILE = pathlib.Path.home() / ".secrets" / "bigbiggerbiggestbot"

SHORT_DESCRIPTION = "Log workouts, track sets, view history & stats. Tap the menu button to open the Mini App."

DESCRIPTION = (
    "Open the Mini App from the menu button below to log workouts, "
    "track sets, view history & stats, and configure settings.\n\n"
    "This bot used to accept slash commands and text-message workouts, "
    "but everything moved into the Mini App. The chat itself is now a "
    "doorway."
)


def call(token: str, method: str, payload: dict) -> bool:
    """Call a Bot API method; return True on success."""
    url = API_BASE.format(token=token, method=method)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if not body.get("ok"):
                print(f"  {method}: API reported error: {body}", file=sys.stderr)
                return False
            print(f"  {method}: ok")
            return True
    except urllib.error.HTTPError as e:
        # Telegram returns 4xx with a JSON error body — read it for the why.
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"raw": str(e)}
        print(f"  {method}: HTTP {e.code} — {err_body}", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"  {method}: network error: {e}", file=sys.stderr)
        return False


def _load_token() -> str:
    """BOT_TOKEN env first, then ~/.secrets/bigbiggerbiggestbot (matches start.py)."""
    token = os.environ.get("BOT_TOKEN", "").strip()
    if token:
        return token
    if SECRETS_FILE.is_file():
        return SECRETS_FILE.read_text().strip()
    return ""


def main() -> int:
    token = _load_token()
    webapp_url = os.environ.get("WEBAPP_URL", "").strip()

    if not token:
        print(f"ERROR: no BOT_TOKEN env var and {SECRETS_FILE} missing/empty", file=sys.stderr)
        return 2
    if not webapp_url:
        print("ERROR: WEBAPP_URL env var is empty", file=sys.stderr)
        return 2
    if not webapp_url.startswith("https://"):
        print(f"ERROR: WEBAPP_URL must be https:// (got {webapp_url!r})", file=sys.stderr)
        return 2

    print(f"Configuring presence — webapp={webapp_url}")

    # Telegram requires the menu button URL to be HTTPS.
    menu_ok = call(token, "setChatMenuButton", {
        "menu_button": {
            "type": "web_app",
            "text": "Open Workout Tracker",
            "web_app": {"url": webapp_url},
        },
    })
    desc_ok = call(token, "setMyDescription", {"description": DESCRIPTION})
    short_ok = call(token, "setMyShortDescription", {"short_description": SHORT_DESCRIPTION})
    # Clear any leftover slash-command list (we used to publish /start etc.).
    cmds_ok = call(token, "setMyCommands", {"commands": []})

    if menu_ok and desc_ok and short_ok and cmds_ok:
        return 0
    print("WARN: at least one presence call failed (see above)", file=sys.stderr)
    # Non-zero so systemd can see something went wrong, but with the `-` prefix
    # on ExecStartPost the service still considers itself healthy.
    return 1


if __name__ == "__main__":
    sys.exit(main())
