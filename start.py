#!/usr/bin/env python3
"""
Orchestrator — single entry point for `nix run`.
  1. Loads BOT_TOKEN from ~/.secrets or .env (same as bot.py)
  2. Starts the API server
  3. Starts localtunnel to get a public HTTPS URL
  4. Starts the Telegram bot with WEBAPP_URL set
  5. Cleans up everything on Ctrl+C
"""
import os
import re
import signal
import subprocess
import sys
import time
import pathlib

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
SECRETS_FILE = pathlib.Path.home() / ".secrets" / "bigbiggerbiggestbot"


def load_token() -> str:
    """Load bot token: secrets file → .env → BOT_TOKEN env var."""
    # 1. Secrets file (same path as bot.py uses)
    if SECRETS_FILE.is_file():
        token = SECRETS_FILE.read_text().strip()
        if token:
            print(f"  Token loaded from {SECRETS_FILE}")
            return token

    # 2. .env in working directory
    env_file = pathlib.Path.cwd() / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip("\"'")
                if token:
                    print(f"  Token loaded from {env_file}")
                    return token

    # 3. Already in environment
    token = os.environ.get("BOT_TOKEN", "").strip()
    if token:
        print("  Token loaded from BOT_TOKEN env var")
        return token

    print("\n  No bot token found!")
    print(f"  Put it in {SECRETS_FILE}")
    print("  Or create a .env file with: BOT_TOKEN=your-token\n")
    sys.exit(1)


def start_server(port: int, bot_token: str) -> subprocess.Popen:
    env = {**os.environ, "API_PORT": str(port), "BOT_TOKEN": bot_token}
    return subprocess.Popen(
        [sys.executable, str(SCRIPT_DIR / "server.py")],
        env=env,
    )


def start_tunnel(port: int) -> tuple[subprocess.Popen, str]:
    print(f"  Starting tunnel to port {port}...")
    proc = subprocess.Popen(
        ["lt", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    url = None
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                print("  Tunnel process exited unexpectedly.")
                break
            continue
        line = line.strip()
        print(f"  [tunnel] {line}")
        match = re.search(r"https?://\S+", line)
        if match:
            url = match.group(0)
            break

    if not url:
        proc.kill()
        print("\n  Could not get a tunnel URL.")
        print("  Make sure localtunnel is working: lt --port 8080\n")
        sys.exit(1)

    return proc, url


def start_bot(bot_token: str, webapp_url: str) -> subprocess.Popen:
    env = {**os.environ, "BOT_TOKEN": bot_token, "WEBAPP_URL": webapp_url}
    return subprocess.Popen(
        [sys.executable, str(SCRIPT_DIR / "bot.py")],
        env=env,
    )


def main():
    port = int(os.environ.get("API_PORT", "8080"))
    procs: list[subprocess.Popen] = []

    def cleanup(sig=None, frame=None):
        print("\nShutting down...")
        for p in procs:
            try:
                p.terminate()
            except OSError:
                pass
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print()
    print("  ==========================================")
    print("  BigBiggerBiggest — Fitness Tracker")
    print("  ==========================================")
    print()

    # 1. Load token
    bot_token = load_token()
    masked = bot_token[:5] + "..." + bot_token[-4:]
    print(f"  BOT_TOKEN: {masked}")

    # 2. Start API server
    print(f"\n  Starting API server on port {port}...")
    server = start_server(port, bot_token)
    procs.append(server)
    time.sleep(1)

    if server.poll() is not None:
        print("  Server failed to start!")
        sys.exit(1)

    # 3. Start tunnel
    tunnel, webapp_url = start_tunnel(port)
    procs.append(tunnel)

    # 4. Start bot
    print(f"\n  WEBAPP_URL: {webapp_url}")
    print("  Starting bot...\n")
    bot = start_bot(bot_token, webapp_url)
    procs.append(bot)

    print("  ==========================================")
    print(f"  All systems go!")
    print(f"  Mini App: {webapp_url}")
    print(f"  API:      http://localhost:{port}")
    print(f"  Press Ctrl+C to stop")
    print("  ==========================================")
    print()

    while True:
        for p in procs:
            ret = p.poll()
            if ret is not None:
                name = {id(server): "Server", id(tunnel): "Tunnel", id(bot): "Bot"}.get(id(p), "?")
                print(f"\n  {name} exited with code {ret}")
                cleanup()
        time.sleep(1)


if __name__ == "__main__":
    main()
