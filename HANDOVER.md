# TeammateX — Handover

_Updated 2026-05-26 (after the agent rearchitecture + the knowledge-pipeline fixes)._

## What the app does
An AI teammate that learns your codebases. You onboard repos (GitHub URLs); it
builds a Neo4j knowledge graph + pgvector embeddings, then you chat with it via a
web UI. It has a real shell and can investigate, edit, run tests, and open PRs on
its own — there are no scripted workflows; the model drives the tools.

## Tech stack
- **Backend**: FastAPI + Celery + Neo4j + PostgreSQL (pgvector) + Redis
- **Frontend**: Next.js + Tailwind (dark theme)
- **LLM**: DeepSeek `deepseek-v4-flash` via litellm (non-thinking — best for tool loops).
  Claude/GPT are supported as higher-reliability upgrades (see "Switching model").
- **Containers**: 9 services (caddy, api, frontend, postgres, neo4j, redis, worker×2, worker-beat).
  `gh`, `git`, and **node 22 + npm** are installed in the api/worker images.

### Login
- URL: http://localhost:3000 — `admin@teammatex.local` (local test password set during setup).

## Run it
```bash
cd /home/dev/Downloads/code/teammatex
docker compose up -d                          # start
docker compose exec api alembic upgrade head  # migrations (first run)
docker compose stop                           # pause (keeps data)
docker compose down                           # stop + remove containers (keeps volumes)
docker compose down -v                        # WIPE everything (repos, graph, DB, chat)
```

## Useful commands
```bash
docker compose ps                                   # service health
docker logs teammatex-api-1 --tail 20               # API logs
docker exec teammatex-postgres-1 psql -U teammatex -d teammatex -c "SELECT count(*) FROM code_embeddings;"
docker exec teammatex-neo4j-1 cypher-shell -u neo4j -p change-me-neo4j "MATCH (n) RETURN labels(n)[0] AS t, count(*) ORDER BY count(*) DESC"
```

## Dev loop (code is baked into the image — no bind mount)
```bash
# Quick source change without a 5-min rebuild:
docker cp backend/app/<path>.py teammatex-api-1:/app/app/<path>.py
docker cp backend/app/<path>.py teammatex-worker-1:/app/app/<path>.py   # + worker-2, worker-beat for pipeline code
docker compose restart api worker worker-beat
# Tests (prod image, install dev deps once):
docker exec teammatex-api-1 pip install -q pytest pytest-asyncio
docker exec teammatex-api-1 python -m pytest tests/ -q
# Persist everything (node/gh/ddgs + code): docker compose build api worker
```
Only `pyproject.toml`/`package.json`/Dockerfile changes need `docker compose build`.

## Knowledge pipeline (the differentiator) — how it works now
- **Embeddings** (`code_embeddings`, pgvector): `vector(384)` for the local
  `all-MiniLM-L6-v2` model. The onboarding embedding stage derives the dimension
  from the model and self-corrects a table created at the wrong dimension. Search:
  `EmbeddingService.search` / the `semantic_search` tool.
- **Graph** (Neo4j): `Repository`, `File`, `Function`, `Module`, `Class` joined by
  `PART_OF`, plus `CALLS` edges between functions (caller → callee). Files/Functions
  carry `repo_id`. Tools: `get_architecture` (files ranked by function count),
  `graph_query` (name search), and `find_dependents`/`find_dependencies` (who calls X /
  what X calls). All scope by repo id/name or span all repos. Re-onboard to populate.
- These knowledge tools are all in the chat agent's tool set.

## Switching model (DeepSeek default → Claude/GPT)
DeepSeek is the cheap default. To use a stronger model for higher tool-calling
reliability, save an `llm_config` row:
```bash
curl -X PUT http://localhost:8000/api/config/llm_config -H "Content-Type: application/json" \
  -d '{"key":"llm_config","value":{"provider":"anthropic","api_key":"<key>","model":"claude-sonnet-4-6"}}'
```
`GET /api/config/llm/providers` lists recommended providers/models and the active one.

## GitHub tokens
PRs need a token with **Contents: write + Pull requests: write** (or classic `repo`).
`POST /api/config/github_token/verify` reports whether the stored/given token can
push (read-only tokens clone but 403 on push). git+gh auth self-heals on the first
chat after a token is added — no restart needed.

## Known limitations / not-yet-done
- `pr_reviewer` and the Slack bot need live inputs/config to exercise end to end.
- `test_api.py` has pre-existing failures (endpoint tests that need DB fixtures); not
  a regression — see the suite baseline.

## See also
- `TODO.md` — prioritized backlog and continuation notes.
- `SECURITY.md` — the (intentional) full-access posture and secret-handling rules.
