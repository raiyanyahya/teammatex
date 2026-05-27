# WS2 — Dashboard → real overview

_Date: 2026-05-27_

## Problem

The landing page (`/dashboard`) is a permanent "Get started" checklist. The teammate
name is read from `localStorage` (not the server), so on any fresh browser it shows
"Name your teammate" and the bar sits at 3/4 forever. Even at 4/4 the page stays a
checklist; it never becomes a real dashboard. (It also carries more dead Slack/Jira
inputs in the `done===4` block.)

## Design

**Name hydration + rename.** In `load()`, read `GET /api/config` →
`config.teammate_name.name` as the source of truth (localStorage is just a cache).
Name is editable any time via an inline pencil in the overview header — not a one-shot.

**Setup = functional essentials.** `configured = hasLLM && hasGithub && repos > 0`.
Naming is cosmetic and no longer blocks (it moves to the overview header). This kills
the "always incomplete" feeling.

- **Not configured →** existing first-run checklist (now with the name hydrated).
- **Configured →** an Overview (new `components/dashboard/Overview.tsx`) replacing the
  checklist (and the dead `done===4` Slack/Jira block):
  - Greeting "**`<name>`** is watching N repositories" with an inline rename pencil.
  - **Ask box** — routes to `/chat?q=<question>`; the chat page consumes `?q=` to
    prefill/auto-send (small wire so the box isn't a fake control).
  - Four cards, each linking to its page:
    - **Repositories** — count + "X fully onboarded · Y in progress" (per-repo
      `/api/repos/{id}/onboarding`, 12/12 = onboarded).
    - **Today's standup** — PRs / tasks / blockers counts (`/api/features/standup`).
    - **Recent activity** — last 5 entries (`/api/knowledge/audit?limit=5`).
    - **Usage** — total tokens + `$${total_cost_cents/100}` (`/api/knowledge/costs/summary`).

## Testing

Frontend-only (all endpoints exist). Verify in the running app via headless Chrome:
configured state shows the overview with 4 cards + correct repo count (4) and cost
($11.78); the name hydrates from the server; the ask box lands on chat with the query;
the checklist still renders when unconfigured.

## Out of scope

Per-card detail/expansion, time-range filters, and the still-unwired settings controls
(handled honestly in WS1).
