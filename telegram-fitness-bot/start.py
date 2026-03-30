#!/usr/bin/env python3
"""
Orchestrator — the single entry point for `nix run`.
  1. Loads BOT_TOKEN from .env in the current directory
  2. Starts the API server
  3. Starts a localtunnel to get a public HTTPS URL
  4. Starts the Telegram bot with that URL
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


def load_dotenv():
    """Load .env from the working directory (where the user ran `nix run`)."""
    env_file = pathlib.Path.cwd() / ".env"
    if not env_file.exists():
        # Also check next to the script (for non-nix usage)
        env_file = SCRIPT_DIR / ".env"
    if not env_file.exists():
        return

    print(f"Loading secrets from {env_file}")
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                os.environ.setdefault(key, value)


def check_token():
    token = os.environ.get("BOT_TOKEN", "")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("\n  No BOT_TOKEN found!\n")
        print("  Create a .env file in this directory with:")
        print("    BOT_TOKEN=your-token-from-@BotFather\n")
        sys.exit(1)
    # Mask token in logs
    masked = token[:5] + "..." + token[-4:]
    print(f"  BOT_TOKEN: {masked}")
    return token


def start_server(port: int) -> subprocess.Popen:
    """Start the aiohttp API server."""
    env = {**os.environ, "API_PORT": str(port)}
    return subprocess.Popen(
        [sys.executable, str(SCRIPT_DIR / "server.py")],
        env=env,
        cwd=pathlib.Path.cwd(),  # DB writes go to user's working directory
    )


def start_tunnel(port: int) -> tuple[subprocess.Popen, str]:
    """Start localtunnel and return (process, public_url)."""
    print(f"  Starting tunnel to port {port}...")

    proc = subprocess.Popen(
        ["lt", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # localtunnel prints "your url is: https://xxx.loca.lt"
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


def start_bot(webapp_url: str) -> subprocess.Popen:
    """Start the Telegram bot with the tunnel URL."""
    env = {**os.environ, "WEBAPP_URL": webapp_url}
    return subprocess.Popen(
        [sys.executable, str(SCRIPT_DIR / "bot.py")],
        env=env,
        cwd=pathlib.Path.cwd(),
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
    print("  Telegram Fitness Bot")
    print("  ==========================================")
    print()

    # 1. Load .env
    load_dotenv()
    check_token()

    # 2. Database will be created in the working directory
    db_path = os.environ.setdefault("DB_PATH", str(pathlib.Path.cwd() / "fitness.db"))
    print(f"  Database: {db_path}")

    # 3. Start API server
    print(f"\n  Starting API server on port {port}...")
    server = start_server(port)
    procs.append(server)
    time.sleep(1)  # Give it a moment to bind

    if server.poll() is not None:
        print("  Server failed to start!")
        sys.exit(1)

    # 4. Start tunnel
    tunnel, webapp_url = start_tunnel(port)
    procs.append(tunnel)

    # 5. Start bot
    print(f"\n  WEBAPP_URL: {webapp_url}")
    print(f"  Starting bot...\n")
    bot = start_bot(webapp_url)
    procs.append(bot)

    print("  ==========================================")
    print(f"  All systems go!")
    print(f"  Mini App: {webapp_url}")
    print(f"  API:      http://localhost:{port}")
    print(f"  Press Ctrl+C to stop")
    print("  ==========================================")
    print()

    # Wait for any process to exit
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
