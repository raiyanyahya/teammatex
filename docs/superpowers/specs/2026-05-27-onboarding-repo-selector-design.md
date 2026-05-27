# Onboarding Repo Selector — Design

_Date: 2026-05-27_

## Goal

During onboarding, let the user browse the GitHub repos their connected token can
see, **select-all by default**, and deselect the ones they don't want before
onboarding the rest in one action. Today onboarding only accepts one pasted repo
URL at a time (or a hidden "paste an org name imports *everything*" path with no
selection).

## Context

- `GET /api/github/repos` (`backend/app/api/integrations.py`) lists the account's
  repos from `/user/repos` (per_page 50, sort updated), returning
  `{repos: [{name (full_name), url (clone_url), default_branch, private, language}]}`.
- `POST /api/repos {github_url}` (`backend/app/api/repos.py`) adds one repo, dedups
  on exact `github_url`, and kicks off the 12-stage onboarding pipeline
  (`start_onboarding`). A `clone_url` works (the name strips `.git`). Passing just an
  org/user name imports *all* of its repos — no per-repo selection.
- The onboarding page (`frontend/src/app/onboarding/page.tsx`) shows a paste box when
  there are 0 repos, otherwise a repo list + per-repo pipeline progress.

## Approach (chosen)

An inline selector on the onboarding page over a thin bulk endpoint, reusing the
existing per-repo add+onboard logic. Rejected: the org-import path (no per-repo
selection — the whole point), and a pure client-side loop over `POST /repos` (N
requests + partial-failure handling in the UI, no atomic summary).

## Backend

- **`GET /api/github/repos`** also returns `fork` and `archived` per repo (default
  `false` on the SCM-registry fallback path that lacks them). New shape:
  `{name, url, default_branch, private, language, fork, archived}`.
- **`POST /api/repos/bulk {github_urls: [str]}`**: for each url, skip if a `Repo` with
  that `github_url` already exists, else create it and `start_onboarding`. Returns
  `{added: [{url, repo_id, local_name}], skipped: [url, ...]}`. The single
  `POST /api/repos` and the org-import path are unchanged.

## Frontend (`onboarding/page.tsx`)

- A **"Browse my repositories"** button, shown in both the empty state and atop the
  repo list. It loads `/github/repos` + the existing `/repos`, then opens an inline
  selector panel.
- **Already-added detection** is by normalized `owner/repo` slug: parse each existing
  repo's `github_url` to a slug and compare against the discovered repo's `name`
  (which is `full_name`). Robust to `.git` / trailing-slash / http(s) differences.
- **Smart defaults:** a row starts checked iff it is *not* already-added AND *not* a
  fork AND *not* archived. Forks/archived stay visible (user can re-check). Already-added
  rows are disabled and shown as "added" (cannot be re-added from the selector).
- Each row: checkbox, `owner/repo`, language, and badges (`private` / `fork` /
  `archived` / `added`). A **Select all / none** toggle and a live **"Onboard N
  selected"** button → `POST /api/repos/bulk` with the checked clone_urls → close the
  panel and refresh the repo list (the existing pipeline view takes over).
- The manual paste box stays as a secondary "add by URL" option.

## Testing

- Backend: `POST /api/repos/bulk` creates new repos, skips an already-existing
  duplicate, and returns both lists; `GET /api/github/repos` shape includes
  `fork`/`archived` (asserted via the SCM-fallback or a mocked client).
- Frontend: load `/onboarding` in the running app, open the selector, confirm smart
  defaults + select-all + onboard wiring (headless-Chrome screenshot, authenticated).

## Out of scope (YAGNI)

Pagination beyond GitHub's 50/page, org/team pickers, per-repo branch selection, and
re-onboarding already-added repos from the selector.
