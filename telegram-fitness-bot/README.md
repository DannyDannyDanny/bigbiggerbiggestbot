# Telegram Fitness Bot — Mini App

A Telegram bot + Mini App for tracking gym workouts. Log exercises, sets, reps, and weight right inside Telegram.

## Quick Start

### 1. Get a bot token

Message [@BotFather](https://t.me/BotFather) on Telegram and create a new bot.

### 2. Create a `.env` file

```bash
echo 'BOT_TOKEN=your-token-here' > .env
```

### 3. Run

```bash
nix run
```

That's it. The app will:
- Load your `BOT_TOKEN` from `.env`
- Start the API server on port 8080
- Open a localtunnel to get a public HTTPS URL
- Start the bot with that URL wired in
- Create `fitness.db` in the current directory

Open your bot in Telegram and tap the **Workout** menu button.

## Architecture

```
┌───────────────────────┐     ┌─────────────────────────┐
│   Telegram Bot        │     │   API Server (aiohttp)  │
│   (python-telegram-   │     │                         │
│    bot, polling)      │     │   GET/POST /api/*       │
│                       │     │   Static /webapp/*      │
│   /start /workout     │     │                         │
│   /finish /history    │     │   ← Telegram initData   │
└───────────┬───────────┘     │     validation (HMAC)   │
            │                 └────────────┬────────────┘
            │                              │
            └──────────┬───────────────────┘
                       │
                ┌──────┴──────┐
                │   SQLite    │
                │  fitness.db │
                └─────────────┘
```

## Project Structure

```
├── flake.nix        # Nix flake — `nix run` entry point
├── start.py         # Orchestrator: loads .env, starts server + tunnel + bot
├── bot.py           # Telegram bot (commands, reminders)
├── server.py        # aiohttp API + static file server
├── database.py      # SQLite data layer
├── config.py        # Environment-based config
├── .env             # Your BOT_TOKEN (not committed)
├── .envrc           # direnv — auto-activates nix develop
└── webapp/
    ├── index.html   # Mini App entry point
    ├── style.css    # Telegram-native themed styles
    └── app.js       # Frontend logic
```

## Development

```bash
# Enter dev shell with all dependencies
nix develop

# Or with direnv
direnv allow

# Run directly
python start.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_TOKEN` | — | Telegram bot token (required, loaded from `.env`) |
| `API_PORT` | `8080` | API server port |
| `DB_PATH` | `./fitness.db` | SQLite database file path |

`WEBAPP_URL` is set automatically by the localtunnel — you never need to touch it.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/exercises` | List user's exercises |
| POST | `/api/exercises` | Create exercise `{name}` |
| DELETE | `/api/exercises/:id` | Delete exercise |
| GET | `/api/workouts` | Recent workouts with summaries |
| GET | `/api/workouts/active` | Current active workout |
| POST | `/api/workouts` | Start new workout |
| POST | `/api/workouts/:id/finish` | Finish workout |
| GET | `/api/workouts/:id/sets` | Sets in a workout |
| POST | `/api/workouts/:id/sets` | Log a set `{exercise_id, reps, weight}` |
| DELETE | `/api/sets/:id` | Delete a set |

All API requests require the `X-Telegram-Init-Data` header for authentication.
