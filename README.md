# BigBiggerBiggestBot 💪

A Telegram bot for logging gym workouts, with an embedded Mini App.

Send workouts as plain text, forward them from Saved Messages, or tap
through a structured log form inside Telegram. History, stats, notes,
edit & delete, JSON/CSV export — all per-user, all in SQLite.

## Format

Send messages like:

```
Bench press: 4x8x35
Shoulder press (3032): 8x25, 5x35, 6x40
Pull-ups: 3x10
```

- `SETSxREPSxWEIGHT` — uniform sets
- `REPSxWEIGHT, REPSxWEIGHT, ...` — per-set (weight/reps vary)
- Omit weight for bodyweight exercises
- `(machine_id)` is optional (gym equipment ID)
- Blank line separates superset groups; consecutive lines form a superset
- Both `,` and `.` work as decimal separators

## Commands

- `/start` — help & open Mini App
- `/history` — recent workouts
- `/stats` — summary (total workouts, sets, volume)
- `/delete <id>` — soft-delete a workout
- `/export` — download all data as JSON
- `/feedback <text>` — send feedback to the bot author

## Run locally

```bash
nix run
```

This launches:
- API server (port 8080)
- cloudflared tunnel for the Mini App
- Telegram bot (polling)

Put your bot token (from [@BotFather](https://t.me/BotFather)) in
`~/.secrets/bigbiggerbiggestbot` or a `.env` file:

```
BOT_TOKEN=123456:your-bot-token-here
```

`nix develop` drops you into a dev shell with Python + deps.

## Tests

```bash
nix develop --command pytest tests/ -v
```

## Deployment

Runs as a systemd service. A timer pulls this repo periodically and
restarts the service when the remote has new commits — push to `main`
and the bot redeploys itself within ~15 minutes.

The SQLite database lives next to the code at `workouts.db` (gitignored).

## Architecture

- `bot.py` — Telegram command handlers, polling, message parsing
- `server.py` — aiohttp REST API + static file server for the Mini App
- `db.py` — SQLite data layer (workouts, supersets, exercises, feedback; soft delete)
- `parser.py` — workout text → structured data
- `webapp/` — Mini App (HTML/CSS/vanilla JS, Telegram WebApp SDK)
- `start.py` — orchestrator: starts server + tunnel + bot, wires up the Mini App URL
- `tests/` — pytest suite for parser + db

## License

MIT — see [LICENSE](LICENSE).
