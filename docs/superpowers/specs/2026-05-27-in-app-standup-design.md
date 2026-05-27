# In-app Standup — Design

_Date: 2026-05-27_

## Goal

Surface the daily standup **inside the web app** as a dedicated, deterministic
page — not via Slack and not as a free-text chat answer. The teammate's standup
(what happened yesterday, what's active today, what it's blocked on) should be a
real place in the product that loads instantly and reads the same way every time.

## Context

- `StandupGenerator` (`backend/app/services/agent/proactive.py`) already produces a
  standup dict: `name`, `date`, `yesterday` (PRs in the last 24h, formatted string),
  `today` (active tasks, formatted string), `blockers` (hardcoded `"None"`), and a
  structured `prs` list.
- `POST /api/features/standup` returns that dict; `POST /api/features/standup/post`
  pushes it to Slack. No UI calls the read endpoint — it's orphaned.
- The chat page has a "Standup" capability card that sends *"Give me a standup of
  recent activity."* and relies on the LLM to answer (non-deterministic).
- `BlockedTask` (`backend/app/models/blocked.py`) records real blockers: when the
  teammate gets stuck it stores a `question` with `status` `pending`/`answered`.
  Pending rows are genuine blockers — the right source for the Blockers section.

## Approach (chosen)

Reuse and enrich the existing generator + endpoint rather than build a parallel
read-model. Lowest-risk, leans on tested code, and fills the one real gap (blockers
were a placeholder). Rejected alternatives: a new standup service (duplicates the
generator) and a pure-frontend fan-out across list endpoints (spreads standup logic
into the UI).

## Backend

`StandupGenerator.generate()` returns the same dict, plus two structured arrays so
the page can render richly without re-parsing strings:

- `tasks`: the active tasks it already fetches (currently only formatted into the
  `today` string) — `[{title, status, priority}]`.
- `blockers_list`: `BlockedTask` rows where `status == "pending"`, newest first —
  `[{question, created_at}]`.

The existing string fields (`yesterday`, `today`, `blockers`, `prs`) are preserved
for the Slack path's backward-compatibility. The `blockers` **string** changes from
the hardcoded `"None"` to a real summary (e.g. `"None"` when empty, otherwise a count)
derived from `blockers_list`.

Add `GET /api/features/standup` returning the generated payload (page load is
read-only; GET is the right verb). The existing `POST /api/features/standup` and
`POST /api/features/standup/post` (Slack) are unchanged.

## Frontend

- **Sidebar:** new entry "Standup" (lucide `ListChecks`, matching the chat card icon),
  placed near Chat/Tasks.
- **`src/app/standup/page.tsx`:** client component following existing page conventions
  (AuthGuard via layout, `fetch`, Tailwind, lucide icons). Layout:
  - Header: teammate name + date, plus a **Refresh** button that re-fetches.
  - **Yesterday** card: PRs — `title · status · branch`. Empty: "No PR activity."
  - **Today** card: tasks — `title · status · priority`. Empty: "Monitoring for new tasks."
  - **Blockers** card: pending questions, each with its age. Empty: an "All clear" state.
  - Per-section loading skeleton and graceful error state on fetch failure.

## Testing

- Backend test: seed a recent PR + an active task + a `pending` BlockedTask (and one
  `answered` BlockedTask), call `GET /api/features/standup`, assert the PR appears in
  `prs`, the task in `tasks`, the pending question in `blockers_list`, and the answered
  one is excluded.
- Frontend: verified by loading `/standup` in the running app (data renders, refresh works).

## Out of scope (YAGNI)

Scheduling/cron, Slack delivery, per-repo filtering, standup history, and any
AI-generated narrative. Deterministic data only.
