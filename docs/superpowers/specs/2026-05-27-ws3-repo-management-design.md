# WS3 — Repo management

_Date: 2026-05-27_

## Problem

Adding more repos meant re-typing a URL one at a time; the "Browse my repositories"
bulk selector existed only on `/onboarding`. The Repos page had no remove, no re-sync,
and "View pipeline" always landed on the first repo.

## Design

**Shared selector (refactor).** Extract the selector from `onboarding/page.tsx` into
`components/RepoSelector.tsx` — self-contained: fetches `/api/integrations/github/repos`
+ takes `existing` repos for already-added detection (by `owner/repo` slug), applies the
smart default (uncheck already-added / forks / archived), bulk-onboards via
`/api/repos/bulk`, and calls `onDone()` so the parent refreshes. Onboarding and Repos
pages both render it; the onboarding page drops its ~110-line inline copy.

**Repos page management.**
- "Browse my repositories" button → the shared selector (the no-retype path).
- Per repo: **Re-sync** (`POST /api/repos/{id}/retry`), **Remove** (inline confirm →
  `DELETE /api/repos/{id}`), and **View pipeline** → `/onboarding?repo=<id>`.

**Deep-link.** Onboarding reads `?repo=<id>` from `window.location` in `loadRepos` and
selects that repo (falls back to the first) — so "View pipeline" opens the right one.

**Backend.** New `DELETE /api/repos/{id}`: 404 if missing, else delete the child FK rows
(`PR`, `RepoOnboardingState`, `TechDebtItem`, `DependencySnapshot`), then the repo, then
a best-effort `MATCH (n {repo_id:$id}) DETACH DELETE n` graph cleanup (wrapped in
try/except so the DB delete is authoritative).

## Out of scope (noted)

The cloned checkout under `/data/repos` and the pgvector embeddings (no FK to `repos`)
are left for a separate cleanup pass; Remove clearly removes the repo from TeammateX's
DB + graph.

## Testing

Backend TDD: `DELETE` removes the repo + a child PR row and 404s for a missing id (added
to the suite — 201 passed). Frontend verified live (headless Chrome, non-destructive):
Browse + Re-sync + Remove(+confirm) controls present, selector opens from the Repos page
(50 repos), and `/onboarding?repo=<2nd id>` selects build-pipe-frk (not the first repo).
