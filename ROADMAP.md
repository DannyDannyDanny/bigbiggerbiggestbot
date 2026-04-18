# BigBiggerBiggestBot — Roadmap

## Immediate bugs
- [x] **#6** Can't save workout with only one exercise — investigate structured editor save path

## Next
- [x] **#1** Hide "next exercise" affordance until current exercise has ≥1 set
- [x] Version display in Mini App footer — format `YYYY-MM-DD <short-sha>`. Primary path uses `git log`, pure-Python fallback parses `.git/HEAD` + loose commit objects for environments without git on PATH.
- [ ] Semantic versioning tags — start tagging releases (`v0.1.0`, `v0.2.0`, ...) so the footer shows a human version instead of a SHA.
- [ ] **#7** Per-user workout numbering display (global ID stays as real key, just display transform)

## Soon
- [ ] **#2** Superset support in structured editor — backend already supports it; UI needs a "group with previous" toggle or drag-to-group
- [ ] Exercise name standardization — OHP = shoulder press = military press. Aliases table.
- [ ] Global exercise name suggestions — autocomplete should draw from all users' exercises, not just the current user's history.
- [ ] **#3** Machine-to-muscle mapping — reference dataset + `/machine <id>` command. Seeded with gym80 IDs.
- [ ] Interaction / event logging — structured audit of user actions (command usage, Mini App opens, per-set additions with timestamps). Foundation for the rest-timer and future telemetry.
- [ ] Staging via shipyard — new features and fixes must be verified against the shipyard bot (separate Telegram bot) before merging to `main` and triggering the production deploy.

## Later
- [ ] **#8** Workout templates — save/load favorite workouts
- [ ] Per-exercise history — "show me all my squat sessions"
- [ ] Mini-app UI polish (loading states, skeleton screens)
- [ ] News section — surface new features/fixes on release. Delivery TBD: Mini App panel, occasional bot broadcast, or both.
- [ ] Profile / settings — per-user preferences (language, units, etc.)
- [ ] Rest timer — show time since the last set was completed (depends on per-set timestamps from the interaction logging item; gated by a profile/settings toggle so users can turn it off).
- [ ] Cardio tracking — separate data model (duration, distance, pace) alongside strength workouts
- [ ] About section — Mini App panel with pre-alpha / use-at-own-risk disclaimer, version, license link.

## Later later
- [ ] Per-exercise graphs/trends
- [ ] **#5** AI image generator describing workout (novelty)
- [ ] Replace cloudflared — unlocks BotFather permanent URL

## Feedback reference
Raw feedback from `/feedback` command queryable via:

```
sqlite workouts.db "SELECT * FROM feedback ORDER BY created_at DESC;"
```
