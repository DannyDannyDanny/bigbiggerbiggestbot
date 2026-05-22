# BigBiggerBiggestBot — Roadmap

## Immediate bugs
- [x] **#6** Can't save workout with only one exercise — investigate structured editor save path

## Next
- [x] **#1** Hide "next exercise" affordance until current exercise has ≥1 set
- [x] Version display in Mini App footer — format `YYYY-MM-DD <short-sha>`. Primary path uses `git log`, pure-Python fallback parses `.git/HEAD` + loose commit objects for environments without git on PATH.
- [x] ~~Semantic versioning tags — start tagging releases (`v0.1.0`, `v0.2.0`, ...) so the footer shows a human version instead of a SHA.~~ Decided against — keeping `YYYY-MM-DD <short-sha>` format.
- [x] **#7** Per-user workout numbering display (global ID stays as real key, just display transform). `/delete <n>` now uses the per-user number too. Deleting renumbers later workouts down.

## Soon
- [ ] **#2** Superset support in structured editor — backend already supports it; UI needs a "group with previous" toggle or drag-to-group
- [ ] Exercise name standardization — OHP = shoulder press = military press. Aliases table.
- [x] Global exercise name suggestions — autocomplete draws from all users' exercises, ordered by popularity, case-insensitively grouped.
- [ ] **#3** Machine-to-muscle mapping — reference dataset + `/machine <id>` command. Seeded with gym80 IDs.
- [x] Interaction / event logging — structured `events` table; bot commands, workout save/update/delete, Mini App opens, and per-set additions all record events. `POST /api/events` endpoint lets the Mini App emit client-side events. Rest-timer prereq done.
- [x] Staging via shipyard — Mini-App-only HTTP tenant under `shipyard_poc_bot` (slash-command bot deleted; phantom-ship's Shipyard owns Telegram polling). `fitness-bot-shipyard.service` on sunken-ship watches `origin/staging` from `/home/danny/tg_fitness_bot_shipyard`, listens on `:8081`, fronted by vps-relay Caddy at **https://b3.dannydannydanny.me**, validates initData against `shipyard_poc_bot`'s token (`EnvironmentFile=/home/danny/.secrets/shipyard_poc_bot.env`). Listed in `~/python-projects/26_shipyard/apps.json` as `b3bot-beta`. Workflow: `git push origin <branch>:staging` (auto-deploys ~15 min) → tap **B3Bot beta** in shipyard_poc_bot → test → `git push origin <branch>:main`.
- [x] **feedback #9** Negative weight input — `±` sign-flip button next to the weight input handles iOS numeric keypads that have no minus key; active state indicates a negative value.
- [ ] Last-session recall — when starting an exercise, show the most recent sets/weights logged for it (and pre-fill the weight) so you have a reference for what to beat.

## Later
- [ ] **#8** Workout templates — save/load favorite workouts
- [ ] Per-exercise history — "show me all my squat sessions"
- [ ] Mini-app UI polish (loading states, skeleton screens)
- [ ] Super subtle animations — tasteful micro-transitions (set-row entry/exit, card flips, tab switches). Nothing flashy; just enough to make state changes feel continuous.
- [ ] News section — surface new features/fixes on release. Delivery TBD: Mini App panel, occasional bot broadcast, or both.
- [~] Profile / settings — infrastructure shipped (JSON-blob `user_settings` table, `GET`/`PUT /api/settings`, new Settings tab). First preference wired: rest timer on/off. Units and language still TBD (each needs end-to-end display/input work).
- [x] Rest timer — shows mm:ss since the last set in the current exercise. Client-side state; resets per exercise; survives draft restore. Settings-toggle gate TBD when profile/settings lands.
- [ ] Cardio tracking — separate data model (duration, distance, pace) alongside strength workouts
- [ ] About section — Mini App panel with pre-alpha / use-at-own-risk disclaimer, version, license link.
- [ ] Editable workout timestamp — let users set/change the workout date when logging or editing, so they can backfill old sessions. Current flow always uses server `now()` (Mini App) or the forwarded-message date (bot).

## Later later
- [ ] Per-exercise graphs/trends
- [ ] **#5** AI image generator describing workout (novelty)
- [ ] Replace cloudflared — unlocks BotFather permanent URL

## Feedback reference
Raw feedback from `/feedback` command queryable via:

```
sqlite workouts.db "SELECT * FROM feedback ORDER BY created_at DESC;"
```
