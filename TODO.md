# TeammateX — TODO / Continuation

_Last updated: 2026-05-26. The P0/P1/P2 backlog below has been worked through;
this now records what was done and what genuinely remains._

## Done in this pass

### P0 — knowledge pipeline is now real
- **Embeddings store rows.** Root cause: the table was `vector(1536)` while the local
  `all-MiniLM-L6-v2` model emits 384, so every insert hit `expected 1536 dimensions`
  and the error was swallowed (`except: pass`). Fix: derive the dimension from the
  model, self-correct an existing table (`embedding_schema.reconcile_embeddings_dim`),
  insert with per-row savepoints + real error logging, and a collision-free `chunk_id`.
  Migration/model default corrected to match the provider. 4 repos re-embedded (437 rows).
- **Graph returns data.** `get_architecture` queried a `(File)-[:PART_OF]->(Module)`
  topology that the builder never creates; rewritten to the real topology (files ranked
  by function count) + repo_id/name resolution. Also fixed `graph_query` — `KnowledgeGraph.run`
  passed cypher params as `**kwargs`, colliding with the driver's reserved `query` arg.
- **Re-exposed** `semantic_search`, `graph_query`, `get_architecture` in `CORE_TOOLS`
  (verified through the runtime dispatch).

### P1
- **node 22 + npm** installed in the api/worker images (and the running containers).
- **7 bolt-on features audited.** Fixed `auto_sync` (it imported a non-existent
  `proactive_agent` and `memory_manager`, raising on every detected change) — added the
  `memory_manager` singleton, dropped the dead notify. `docs_generator`, `digest`,
  `blame_tracer` smoke-tested OK; `slack_bot` is correctly config-gated.

### P2
- **Token UX.** `POST /api/config/github_token/verify` reports valid + login + push
  rights (read-only vs write); setup page wired to it. Backend done; needs a frontend
  rebuild (`docker compose build frontend`) for the UI change to go live.
- **Stronger model option.** litellm already supports Claude/GPT; modernized stale
  default model ids, added `RECOMMENDED_MODELS` + `GET /api/config/llm/providers`,
  locked the model-name mapping with tests. DeepSeek stays the cheap default.
- **Secrets + posture.** Removed `NEXT.md` (it committed a real DeepSeek key + GitHub PAT)
  and added `SECURITY.md`. **The leaked credentials remain in git history — rotate them.**
- **Docs.** `HANDOVER.md` rewritten to current state; `NEXT.md` retired into `TODO.md`/`SECURITY.md`.

## Remaining / next

- [ ] **Graph has no `CALLS` edges** — the tree-sitter parser doesn't extract calls, so
  `find_dependents`/`find_dependencies` return empty and the call graph is structural-only.
  (`test_parser_chunker::test_parse_detects_calls` is the failing guard.) Fix call
  extraction in `onboarding/code_parser.py`, then re-onboard.
- [ ] **Frontend rebuild** to ship the token-verify UI: `docker compose build frontend`.
- [ ] **Exercise `pr_reviewer` + Slack** end to end with a live PR / Slack token.
- [ ] **Pre-existing `test_api.py` failures** (endpoint tests needing DB fixtures) — wire a
  test database/fixtures so the suite is green, or mark them integration-only.
- [ ] **Persist the image changes**: `docker compose build api worker` bakes node/gh/ddgs
  (currently node was also apt-installed into the running containers, which is ephemeral).

## Reference / gotchas
- DeepSeek-only via DB `app_config.llm_config` (`.env` keys empty). Switch model: see HANDOVER.
- git+gh auth self-heals at chat start (`git_setup.ensure_gh_ready`).
- Code is baked into images; use `docker cp` + `docker compose restart` for quick changes.
- Neo4j password: `change-me-neo4j`. Postgres: `teammatex`/`teammatex`.
