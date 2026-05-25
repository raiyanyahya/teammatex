# TeammateX — TODO / Continuation

_Last updated: 2026-05-26. Reflects state after the agent rearchitecture + fresh reset._

## Where we are

- **Agent core rewritten and working.** Small powerful toolset (bash, file r/w/edit,
  grep/glob, web_search) the model drives itself — no scripted workflows, no leaked
  tool-call markup. Verified end-to-end: it updated deps, committed, pushed, and opened
  a real PR (`blockstacks/kit-fork#1`).
- **Fresh app running.** Login `admin@teammatex.local` / `test1234` at http://localhost:3000.
  DeepSeek configured (`deepseek-v4-flash`); a write-enabled GitHub token is set.
- **66 unit tests pass** (`tests/test_message_utils|web_search|environment|agent_loop|provider|git_setup|tools`).
- New modules: `agent/{loop,message_utils,web_search,environment,git_setup}.py`.

## Dev loop / how to run

```bash
docker compose up -d && docker compose exec api alembic upgrade head
# Quick code change (image is baked, not bind-mounted):
docker cp backend/app/.../file.py teammatex-api-1:/app/app/.../file.py && docker compose restart api
# Tests (prod image omits dev deps):
docker exec teammatex-api-1 pip install -q pytest pytest-asyncio
docker exec teammatex-api-1 python -m pytest tests/ -q
# Persist everything: docker compose build api worker worker-beat
```

---

## P0 — Make the core differentiator real (the "knowledge graph" is currently dead)

The whole pitch is "learns your codebase via KG + embeddings," but the agent works by
brute-force `grep`/`read`. Fix this or cut it and lean into "great coding agent."

- [ ] **Embeddings store 0 rows.** Debug the sync insert path (`knowledge/embeddings.py`,
  `onboarding/pipeline.py`) — the `CAST(:emb AS vector)` format in sync SQLAlchemy.
  _Done when:_ re-onboard a repo → `SELECT count(*) FROM code_embeddings` > 0 and
  `semantic_search` returns hits.
- [ ] **Graph returns empty.** `get_architecture(repo_id=…)` → `[]`. Two suspects:
  (a) `knowledge/graph.py` run/param handling; (b) `repo_id` mismatch — the value passed
  (local_name) ≠ the repo_id on the graph nodes. _Done when:_ `graph_query`/`get_architecture`
  return nodes for an onboarded repo.
- [ ] **Re-expose `semantic_search` + `graph_query`** in `runtime.CORE_TOOLS` once they
  actually return data (dropped for now because they were empty and wasted turns).

## P1 — Be a real teammate on the repos it onboards

- [ ] **Install language toolchains in the image** (node+npm at minimum). The container
  can't build/test the JS/Electron repos it onboards — the dep-update agent had to query
  the npm registry by hand. _Done when:_ agent can run `npm install` + `npm test`.
- [ ] **Audit the "7 features" added in one commit.** At least `auto_sync` throws
  `cannot import name 'proactive_agent'` at startup. Verify or disable: `pr_reviewer`,
  `blame_tracer`, `reporting/digest`, `reporting/docs_generator`, `integrations/slack_bot`,
  `auto_sync` — end to end.

## P2 — Robustness & polish

- [ ] **Token UX:** surface read-only vs write status in Settings (read-only tokens clone
  but 403 on push — we lost time to this). A "verify token" check would help.
- [ ] **Stronger model option:** wire Claude/GPT via the existing litellm abstraction for
  higher tool-calling reliability; keep DeepSeek as the cheap default.
- [ ] **Security posture:** runs as root + docker socket mounted + full shell + tokens in
  DB. Decide what's intended; stop committing secrets (`NEXT.md` has live-looking keys).
- [ ] **Stale docs:** `HANDOVER.md` / `NEXT.md` predate the rearchitecture (list fixed bugs
  as open, reference the retired `deepseek-chat`). Update or replace.

## Reference / gotchas

- Agent is DeepSeek-only via DB `app_config.llm_config` (`.env` keys are empty).
- git+gh auth self-heals at chat start (`git_setup.ensure_gh_ready`) — a token added in
  Settings works on the next message, no restart.
- PRs need a token with **Contents: write + Pull requests: write** (or classic `repo`).
