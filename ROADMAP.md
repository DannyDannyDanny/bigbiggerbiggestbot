# BigBiggerBiggestBot — Roadmap

## Immediate bugs
- [ ] **#6** Can't save workout with only one exercise — investigate structured editor save path

## Next
- [ ] **#1** Hide "next exercise" affordance until current exercise has ≥1 set
- [ ] **#7** Per-user workout numbering display (global ID stays as real key, just display transform)

## Soon
- [ ] **#2** Superset support in structured editor — backend already supports it; UI needs a "group with previous" toggle or drag-to-group
- [ ] Exercise name standardization — OHP = shoulder press = military press. Aliases table.
- [ ] **#3** Machine-to-muscle mapping — reference dataset + `/machine <id>` command. Seeded with gym80 IDs.

## Later
- [ ] **#8** Workout templates — save/load favorite workouts
- [ ] Per-exercise history — "show me all my squat sessions"
- [ ] Mini-app UI polish (loading states, skeleton screens)

## Later later
- [ ] Per-exercise graphs/trends
- [ ] **#5** AI image generator describing workout (novelty)
- [ ] Replace cloudflared — unlocks BotFather permanent URL

## Feedback reference
Raw feedback from `/feedback` command queryable via:

```
sqlite workouts.db "SELECT * FROM feedback ORDER BY created_at DESC;"
```
