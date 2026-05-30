# Eval Harness + Citations — Design

**Date:** 2026-05-30
**Status:** Approved (design), pending implementation plan

## Goal

Make the AI teammate's answers *provably* grounded in real code, in two parts:

1. **Citations** — every chat answer shows the source files the agent actually consulted.
2. **Eval harness** — a deterministic, reproducible measurement of retrieval quality (does the teammate surface the *right* code for a question?), runnable as a regression gate.

These are the foundation for trusting the agent on a real codebase. LLM *prose* faithfulness (does the wording match the source?) is explicitly **out of scope** for this iteration.

## Decisions (from brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Citation source | **Auto-extract from tool activity** — deterministic, no model cooperation needed |
| 2 | Eval scope | **Retrieval/citation accuracy, deterministic** (hit@k + MRR); no LLM judge |
| 3 | Corpus & runner | **Self-contained synthetic fixture repo** + reusable engine that can also target a live instance |
| 4 | What the eval scores | The **retrieval primitive** (`semantic_search` + graph lookups), NOT the full LLM agent — so it stays deterministic and token-free |

## Part 1 — Citations

### Where the data comes from
The agent loop (`backend/app/services/agent/loop.py`) already yields per-turn events:
`{type: "tool_start", tool, args}` and `{type: "tool_end", tool, result}`. The files the
agent reads/searches/blames are therefore observable without changing tool behavior.

### Component: `agent/citations.py`
A small, pure module with one responsibility: turn a turn's tool activity into a deduped,
ordered list of sources.

- **Source-producing tools** (allowlist, as built): `semantic_search` (results carry
  `file_path`/`start_line`/`end_line`) plus the file-path-argument tools `read_file`,
  `edit_file`, `write_file`, `get_blame`, `find_owner`.
  - *Deferred fast-follow:* the list-of-paths tools `grep_search`, `glob_search`,
    `find_dependents`, `find_dependencies`, `get_architecture` are NOT yet extracted —
    their result shapes weren't pinned during planning. This only ever *under*-cites
    (never wrong), so it preserves the "provably grounded" intent; extend when their
    shapes are confirmed.
- For each such tool call, extract file path(s) from the tool args and/or result.
- Produce `Source { path, tool, lines? }`, deduped by `path` (first occurrence wins,
  which keeps the entry carrying a line range), preserving discovery order. *`repo` is
  deferred:* chat is single-repo today, so path alone is unambiguous; add `repo` to the
  Source + dedup key when chat goes multi-repo.

This module is pure (input: list of tool-event dicts → output: list of Source dicts) so it
is trivially unit-testable with no DB/LLM.

### Wiring
- The loop accumulates tool events for the turn and, just before completing, emits one new
  SSE event: `{type: "sources", sources: [Source, ...]}`. Emitted once per turn, after the
  final `text` event and before `[DONE]`.
- No change to existing event types → backward compatible.

### Frontend
- The chat page handles the new `sources` event type and stores it against the assistant
  message.
- A `Sources` component renders a compact list under the answer: `path · repo` (with the
  line range when present), styled in the existing design language. Empty list → render
  nothing (no "Sources" header when the agent answered from general knowledge).

## Part 2 — Eval harness

### What it scores
The **retrieval primitive**, deterministically. Local MiniLM embeddings are deterministic,
so `semantic_search(question, repo)` yields a reproducible ranked file list. The eval scores
that ranking against expected files. (This is the substrate the citation feature surfaces,
so it is a faithful proxy for "are the citations right?")

### Package: `app/evals/`
- `engine.py` — the reusable core:
  - Input: a golden set — list of `{ id, question, repo, expect_files: [...], expect_owner? }`.
  - For each item: run retrieval (`semantic_search`, repo-scoped) → ranked list of file paths;
    optionally run `find_owner` for `expect_owner`.
  - Score per item: **hit@k** (is any `expect_file` in the top-k? default k=3) and **MRR**
    (reciprocal rank of the first expected file).
  - Aggregate: mean hit@k, mean MRR, count, and a per-item pass/detail table.
  - Return a structured `EvalReport` (data, not printing).
- `__main__.py` — CLI wrapper: `python -m app.evals [--golden FILE] [--k 3] [--threshold 0.8]`.
  Prints the report table; exits non-zero if `hit_rate < threshold` → regression gate.
  *Deferred:* a `--instance <url>` live-mode flag is NOT yet implemented — the CLI runs
  in-process. The engine itself is instance-agnostic (`run_eval(db, embedder, …)`), so the
  flag is a trivial add when a live golden set is authored.

### Self-contained fixture (the always-runnable corpus)
- `backend/tests/fixtures/eval_repo/` — ~5 small files with **unambiguous, distinct** content,
  each clearly "about" one thing, e.g.:
  - `auth.py` — a `login()` / token verification.
  - `billing_webhooks.py` — Stripe webhook handling.
  - `queue_retry.py` — retry/backoff logic.
  - `users.py` — user CRUD.
  - `README.md` — project overview.
- The harness's fixture loader `git init`s a throwaway clone of this directory in a temp dir
  and runs the **real onboarding pipeline** (parse → embed → graph) into the test DBs, so the
  eval exercises the actual stack end-to-end (just small). Cleaned up after.
- `backend/app/evals/golden/fixture.yaml` — ~8 questions with known `expect_files`, e.g.
  *"Where do we handle Stripe webhooks?" → billing_webhooks.py*.

### Live mode
The same engine + a hand-authored `golden/<name>.yaml` can be pointed at a populated instance
(`--instance`) for real-corpus signal against actual onboarded repos. Authoring that larger set
is a follow-up, not part of this iteration's deliverable.

## Components & files

**New**
- `backend/app/services/agent/citations.py` — pure source-extraction.
- `backend/app/evals/__init__.py`, `engine.py`, `__main__.py`, `golden/fixture.yaml`.
- `backend/tests/fixtures/eval_repo/{auth.py,billing_webhooks.py,queue_retry.py,users.py,README.md}`.
- `backend/tests/test_citations.py`, `backend/tests/test_evals.py`.
- `frontend/src/components/chat/Sources.tsx` (or inline in the chat page) — renders sources.

**Touched**
- `backend/app/services/agent/loop.py` — accumulate tool events, emit `sources` event.
- `frontend/src/app/chat/page.tsx` — handle `sources` SSE event, render `Sources`.

## Testing (TDD)

- `test_citations.py` (pure, no DB/LLM):
  - tool events → extracted sources (path parsing per tool shape).
  - dedup by `(path, repo)`; preserves order; prefers entry with line range.
  - non-source tools (e.g. `run_command`) produce no sources.
- `test_evals.py`:
  - scoring math on canned rankings (hit@k true/false at boundary, MRR reciprocal-rank).
  - threshold → exit-code logic.
  - one **end-to-end** run: onboard the fixture repo, run `fixture.yaml`, assert aggregate
    hit@3 meets a sane floor and a known question hits its expected file at rank 1.

## Risks / notes

- **Environment:** the end-to-end eval needs Postgres (pgvector) + Neo4j + local embeddings —
  the same environment the existing `test_api.py` integration suite uses. It runs wherever that
  suite runs (today: the api container). It becomes a true **CI gate** once CI runs those
  service containers — tracked separately; we will not overclaim it gates in CI today.
- **Fixture onboarding:** reuse the real pipeline against a `git init`'d temp clone so the eval
  tests the genuine parse→embed→graph path, not a mock. If pipeline entry requires a remote URL,
  the loader adapts (local path / `file://`) — an implementation detail for the plan.
- **Determinism:** depends on local MiniLM embeddings being deterministic for identical input,
  which they are. If `EMBEDDING_PROVIDER=openai`, the deterministic guarantee weakens — the eval
  documents that it assumes local embeddings.

## Out of scope (deferred)

- LLM-judged answer faithfulness.
- A hand-authored live golden set against the charmbracelet repos (engine supports it; authoring later).
- An in-app `/evals` dashboard page.
- Inline `[1][2]` citation markers in prose (we show a Sources list, not inline markers).
