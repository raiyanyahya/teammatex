# TeammateX — TODO / Continuation

_Last updated: 2026-05-27. The P0/P1/P2 backlog below has been worked through;
this now records what was done and what genuinely remains._

## Done 2026-05-27

- **Frontend healthcheck fixed.** Next.js standalone `server.js` binds to
  `$HOSTNAME`, which Docker auto-sets to the container id (resolves to the eth0
  IP only), so the `localhost:3000` healthcheck always got ECONNREFUSED and the
  container showed `unhealthy` even though it served fine on the published port.
  Forced `HOSTNAME=0.0.0.0` for the frontend service and hardened the probe
  (`127.0.0.1` + an error handler). Now healthy. (commit `adb72f8`)
- **In-app Standup page** (commit `fd8a6aa`). The standup is now a real, deterministic
  place in the product — `GET /api/features/standup` + `/standup` page rendering
  Yesterday (PRs) / Today (tasks) / Blockers (real pending `BlockedTask` rows, no
  longer a hardcoded `"None"`) — instead of only the LLM chat answer or a Slack post.
  This supersedes the old "Batch 3: scheduled standup/digest → Slack" item: standup
  lives in the app, not Slack. Design spec: `docs/superpowers/specs/2026-05-27-in-app-standup-design.md`.
- **Onboarding repo selector** (commit `d7ed957`). A "Browse my repositories" button
  lists the connected account's GitHub repos and onboards a chosen set in one action
  (previously: one pasted URL at a time). `GET /api/integrations/github/repos` now
  returns `fork`+`archived`; `POST /api/repos/bulk {github_urls}` creates+onboards new
  repos and skips already-registered ones. Smart default: everything checked except
  already-added (by `owner/repo` slug, shown disabled), forks, and archived — all still
  visible to re-check. Spec: `docs/superpowers/specs/2026-05-27-onboarding-repo-selector-design.md`.

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

### KG call graph (done)
- **`CALLS` edges now exist.** Two parser bugs: Python calls weren't detected (the
  walker only matched `call_expression`; Python uses `call`), and the caller was
  recorded as the file path instead of the enclosing function (so the builder couldn't
  match it). Fixed in `onboarding/code_parser.py` (recognize `call`/`call_expression`/
  `method_invocation`, track the enclosing function). Re-onboarded → 2,734 CALLS edges.
  `find_dependents`/`find_dependencies` return data and are exposed to the agent
  (repo id/name or all-repos). `test_parse_detects_calls` now passes.

## Done in the test-suite-green pass (2026-05-26)

The whole backend suite is now green — **189 passed, 3 skipped, 0 failed** (the
skips are language-parser-unavailable guards). Highlights:

- **Real async test DB.** `test_api.py` now runs through `httpx.AsyncClient` +
  `ASGITransport` against a real `teammatex_test` Postgres database (the app uses
  async SQLAlchemy + pgvector + JSONB, which SQLite can't model). `conftest.py`
  creates the DB + `vector` extension, builds the schema, and gives each test a
  transaction that rolls back. A session-scoped loop (scoped to `test_api.py`
  only) keeps the Neo4j driver + asyncpg engine on one loop.
- **Real product bugs the tests exposed, fixed:**
  - `proactive.py` standup: missing `timedelta` import, **and** a duplicate sync
    `_get_active_tasks` that shadowed the real async one (it always returned `[]`
    and was being `await`ed → `TypeError`).
  - structlog `event=` kwarg collided with the positional message in three
    webhook log calls (`webhooks.py`, `integrations/github.py`, `integrations/jira.py`)
    → every github/jira webhook 500'd. Renamed to `gh_event`/`jira_event`.
  - `get_onboarding_status` 500'd on a non-UUID id (raw cast → asyncpg DataError);
    now validates the UUID and returns empty stages.
  - `list_github_repos` ignored the injected `get_db` and opened its own session
    against the real DB; now uses dependency injection (testable + consistent).
- **Guardrails hardened:** a hardcoded secret literal (`API_KEY = "..."`) now
  escalates to **BLOCK** (was WARN), so `validate_code` fails it. `check_pr_policy`
  was a stub — now enforces branch convention, PR size, deploy-sensitive paths,
  and deploy freeze. SQL-injection regex now also catches `f"SELECT … %s" % x`.
- **Frontend** rebuilt to drop the trailing `[tool]` markers from chat answers.
- **Images rebuilt** (`docker compose build api worker frontend`) so node/gh/ddgs
  and all the above code fixes are baked in (not just `docker cp`'d).

## Remaining / next

- [ ] **Rotate the leaked credentials** (DeepSeek key + GitHub PAT) — they are still
  in git history at `2d96e61`/`2192484`. This is a **user action**; see `SECURITY.md`.
- [ ] **Exercise `pr_reviewer` + Slack** end to end with a live PR / Slack token.
- [ ] **(optional) Add pytest to the dev image** — the prod image (correctly) omits
  test deps, so the suite needs a one-time `pip install pytest pytest-asyncio` in the
  container, or a dev Dockerfile stage, to run without that step.

## Reference / gotchas
- DeepSeek-only via DB `app_config.llm_config` (`.env` keys empty). Switch model: see HANDOVER.
- git+gh auth self-heals at chat start (`git_setup.ensure_gh_ready`).
- Code is baked into images; use `docker cp` + `docker compose restart` for quick changes.
- Neo4j password: `change-me-neo4j`. Postgres: `teammatex`/`teammatex`.
