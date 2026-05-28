# Resume: dashboard data-wiring

**Status:** Done on `ui-light-refresh` — all five steps below are wired. Keeping the
brief in-tree so the rationale and verification recipe stay discoverable next
time the dashboard surface changes.

## Session gotchas (so you don't relearn these)

- **Run the dev server with `API_URL=http://localhost:8000`** —
  `frontend/next.config.js` proxies `/api/*` to `process.env.API_URL || "http://api:8000"`.
  `api:8000` is the Docker compose DNS name and doesn't resolve from the host,
  so without the override every API call returns a 500 ("Internal Server Error").
- **Frontend dev runs on :3001** — port :3000 is held by the docker-compose
  `teammatex-frontend-1` container (the old UI). Next auto-bumps.
- **Admin password** has been reset in postgres to `test` for
  `admin@teammatex.local`. If login fails, regenerate with
  `docker exec teammatex-api-1 python -c "from app.utils.auth import hash_password; print(hash_password('test'))"`
  then `UPDATE users SET hashed_password = '<hash>' WHERE email = 'admin@teammatex.local';`.
- Backend (`teammatex-api-1`) and postgres are running under docker-compose;
  the frontend `npm run dev` is the only thing on the host.

## Still mocked, by design

- `Live activity` keeps its `DEMO_ACTIVITY` fallback so an empty audit still
  shows the design vocabulary. Real rows take over the moment `/api/knowledge/audit`
  has anything.
- "Suggested asks" pills (`Why is the build slow on kit-fork?`, …) are
  hardcoded prompts, not data — they survive on purpose as onboarding aids.
- `LAST SYNCED 2m ago` next to the hero is still a literal — there's no
  authoritative "graph last refreshed" timestamp source yet. Add one to
  `graph.get_stats` if/when it matters.

## How it's wired now

1. **Hero counts** — `repos` from `/api/repos`, `people` from
   `/api/knowledge/contributors.count`, `concepts` from
   `/api/knowledge/graph/stats.concepts` (sum of File + Module + Function +
   Class node counts; Neo4j has no `Concept` label, so this is the closest
   structural-knowledge total).
2. **Repository health** — `/api/repos` now returns `files`, `open_prs`,
   `onboarding_pct`, `health` per row. `files` is a Neo4j `File`-node count
   (size proxy — the brief's "last commit recency" had no source: there's no
   Commit model or Commit node, and `repos.updated_at` only moves on edit, not
   on git activity). `health = onboarding_pct − min(40, open_prs*5)`, clamped
   0–100. Card sorts by repo order and colors by health (sage ≥85, amber ≥60,
   else rust).
3. **Recent agent runs** card replaces the old `Current Task` card. Reads
   `/api/knowledge/audit` (kept the existing endpoint — there's no canonical
   "agent action" label since no service writes to `AuditLog` today; when one
   appears, filter at the endpoint). Empty audit → "No recent runs."
4. **Sidebar presence** — `uptime` formatted from
   `/api/health.uptime_seconds` (`_API_STARTED_AT` monotonic captured at
   module load; refreshed every 60s on the client), `version` imported from
   `frontend/package.json` at build time. `ctx %` and `IDLE 2m` removed.
5. **Standup rows** — `/api/features/standup` adds `who`/`progress` on each
   task (`assigned_to` + status-bucket: open=10/in_progress=50/review=80) and
   `who` on each PR (parsed from branch convention `feat|fix|chore|wip|users/<name>/...`).
   `TodayCard` renders real rows + empty states for yesterday / today /
   blockers when the DB has nothing.

## Caveats worth knowing

- API container has **no source volume mount**. Repo edits don't reach the
  running container until `docker cp` + `docker restart teammatex-api-1`, or
  a rebuild. Tests run inside the container with `pytest tests/...`.
- `Recent agent runs` (top right) and `Live activity` (bottom left) both read
  from `/api/knowledge/audit` and currently show overlapping rows. Diverge
  them only once `AuditLog` has an `agent_*` action convention to filter on.
- `commits` in repo rows is gone — it was the most-faked field in the old
  card and no upstream produces it. Replaced with `files` from the graph.
  Re-introduce if/when a `Commit` writer exists.

## Files that matter

- `frontend/src/components/dashboard/Overview.tsx` — main dashboard.
- `frontend/src/components/Sidebar.tsx` — presence card.
- `frontend/src/app/globals.css` — design tokens (do not regress).
- `backend/app/api/knowledge.py` — graph + contributors + audit + costs.
- `backend/app/api/repos.py` — where the `health` endpoint goes.
- `backend/app/api/features.py` — standup endpoint.
- `backend/app/services/knowledge/graph.py` — Cypher behind contributors and
  module-graph; reuse patterns there.

## Verifying you're done

Log in at <http://localhost:3001> as `admin@teammatex.local` / `test`. The
dashboard should contain zero of the literal strings above (`7 people`,
`1,247 concepts`, `Reviewing PR #847`, `kit-fork  47 commits`, `uptime 97d`,
etc.) — every visible number should change when you add a contributor, open a
PR, or wait for the next audit row.
