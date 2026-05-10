# BigBiggerBiggestBot 💪

A Telegram **Mini App** for logging gym workouts. History, stats, notes,
edit & delete, JSON/CSV export — all per-user, all in SQLite.

The slash-command bot was removed: the Mini App is the only interface.
A Telegram bot identity (token) is still required so the Mini App can
validate user sessions via `initData` HMAC.

## Workout text format (still supported via "Paste as text" in the Mini App)

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

## Run locally

```bash
nix run
```

This launches:
- API + Mini App server (port 8080)
- cloudflared Quick Tunnel for a public HTTPS URL (skipped if `WEBAPP_URL`
  is already set in the environment, e.g. fronted by a reverse proxy)

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

Two environments share one host (`sunken-ship`):

- **Production** — `fitness-bot.service`, working dir `/home/danny/tg_fitness_bot`,
  watches `origin/main`, served behind a stable URL via the VPS Caddy at
  `https://bbbot.dannydannydanny.me`.
- **Shipyard staging** — `fitness-bot-shipyard.service`, working dir
  `/home/danny/tg_fitness_bot_shipyard`, watches `origin/staging`, served
  by the shared `shipyard_poc_bot` Telegram bot (B3Bot beta is the active
  POC tenant).

Each has its own pull timer that fetches every ~15 minutes and restarts
the service when its branch has new commits.

**Workflow:**

```
git push origin <branch>:staging   # → shipyard auto-deploys, test there
git push origin <branch>:main      # → production auto-deploys
```

Each environment keeps its own `workouts.db` next to its code (gitignored),
so testing on shipyard never touches production data.

## Architecture

- `server.py` — aiohttp REST API + static file server for the Mini App;
  validates Telegram `initData` HMACs against the bot token.
- `db.py` — SQLite data layer (workouts, supersets, exercises, feedback,
  events, settings; soft delete).
- `parser.py` — workout text → structured data (used by the Mini App's
  "Paste as text" path).
- `webapp/` — Mini App (HTML/CSS/vanilla JS, Telegram WebApp SDK).
- `start.py` — orchestrator: loads token, starts server, optionally starts
  cloudflared.
- `tests/` — pytest suite for parser + db.

## License

MIT — see [LICENSE](LICENSE).
