# TeammateX — Handover Document

## Current State (2026-05-25)

### What the app does
TeammateX is an AI teammate that learns your codebase. You onboard repos (GitHub URLs), it builds a Neo4j knowledge graph + pgvector embeddings, then you chat with it via a web UI to ask questions, search code, create PRs, etc.

### Tech Stack
- **Backend**: FastAPI + Celery + Neo4j + PostgreSQL + Redis
- **Frontend**: Next.js 14 + Tailwind CSS (dark theme)
- **LLM**: DeepSeek v4-pro via litellm
- **Docker**: 9 services (caddy, api, frontend, postgres, neo4j, redis, worker×2, worker-beat)

### Services (port)
| Service | Port | Purpose |
|---------|------|---------|
| caddy | 80/443 | Reverse proxy |
| api | 8000 | FastAPI backend |
| frontend | 3000 | Next.js UI |
| postgres | 5432 | Main DB + pgvector |
| neo4j | 7474/7687 | Knowledge graph |
| redis | 6379 | Celery broker |
| worker×2 | - | Celery task workers |
| worker-beat | - | Celery scheduler |

### Login
- URL: http://localhost:3000
- Email: admin@teammatex.local
- Password: test

## How to Start
```bash
cd /home/dev/Downloads/code/teammatex
docker compose up -d
# Wait ~30s for DB init, then run migrations:
docker compose exec api alembic upgrade head
# App ready at http://localhost:3000
```

## How to Stop
```bash
cd /home/dev/Downloads/code/teammatex
docker compose down
```

## How to Wipe Everything (fresh install)
```bash
cd /home/dev/Downloads/code/teammatex
docker compose down -v
docker compose up -d
docker compose exec api alembic upgrade head
```

## Commands to Know
```bash
docker compose ps                          # check service health
docker logs teammatex-api-1 --tail 20      # API logs
docker logs teammatex-worker-1 --tail 20   # worker logs
docker compose exec api alembic upgrade head  # run migrations
docker compose exec neo4j cypher-shell -u neo4j -p change-me-neo4j "MATCH (n) RETURN labels(n)[0] AS type, count(n) ORDER BY count(n) DESC"  # check graph
docker compose exec postgres psql -U teammatex -d teammatex -c "SELECT count(*) FROM code_embeddings;"  # check embeddings
docker compose build api   # rebuild API after code changes (takes ~5 min for full rebuild)
docker compose up -d api   # redeploy rebuilt API
```

## Hot-reload Workaround (avoid 5-min rebuilds)
For quick code changes without rebuilding images:
```bash
# Copy changed files into running containers:
docker cp backend/app/services/agent/runtime.py teammatex-api-1:/app/app/services/agent/runtime.py
docker cp backend/app/services/agent/runtime.py teammatex-worker-1:/app/app/services/agent/runtime.py
docker cp backend/app/services/agent/runtime.py teammatex-worker-2:/app/app/services/agent/runtime.py
docker compose restart api worker
```
Note: This only works for source files. pyproject.toml/package.json changes require `docker compose build`.

## Current Problems

### 1. Agent doesn't chain tools to create PRs
**Symptom**: When asked "update deps and create a PR," the agent reads files, finds deps, but never calls create_branch → edit_file → commit_files → create_pr.
**Root cause**: DeepSeek v4-pro tool-chaining gap. The model CAN chain tools (proven: create_branch → failed → run_command → succeeded) but lacks initiative to switch from "read" to "write" mode.
**What we tried**:
- Reduced tool list from 30+ to 15 (helped with focus)
- Increased iterations from 5 to 8
- Read tools don't count toward empty-result circuit breaker
- Minimal persona prompt (no hardcoded workflows)
**What might help**: Stronger model (Claude, GPT-4), or wiring the LLM to call multiple tools in a single turn.

### 2. Agent sometimes says "I'm Claude" 
**Symptom**: "I'm Claude, built by Anthropic."
**Fix applied**: Persona now says "You are NOT Claude, GPT, or any specific model."
**Status**: Should be fixed, but DeepSeek's training data may override.

### 3. Graph query has parameter name conflict
**Symptom**: `AsyncSession.run() got multiple values for argument 'query'`
**Cause**: graph.py's `run(cql, **params)` method — callers pass `query=query` which conflicts with old param name.
**Fix**: graph.py already renamed parameter to `cql`. May need to verify deployment.

### 4. Embeddings table stores 0 rows
**Symptom**: Embedding stage runs, generates chunks, but INSERTs fail silently.
**Cause**: `CAST(:emb AS vector)` syntax in sync SQLAlchemy context. Vector string format may be wrong.
**Status**: Unresolved. Need to debug the sync embedding pipeline.

### 5. Port 80 conflict with host
**Symptom**: caddy can't bind port 80/443 if host has nginx/apache.
**Fix**: Change caddy ports in docker-compose or stop host web server.

### 6. Build times are painful (~5 min per rebuild)
**Cause**: Poetry resolves 131 deps from scratch when pyproject.toml changes.
**Workaround**: Use `docker cp` hot-reload for source changes. Only rebuild when deps change.

## Key Files Modified (our session)
| File | What changed |
|------|-------------|
| `backend/app/services/agent/runtime.py` | Chat loop, tool dispatch, system prompt, iteration limits |
| `backend/app/services/agent/prompts.py` | Minimal persona, no hardcoded workflows |
| `backend/app/services/knowledge/graph.py` | Content-addressed IDs, run/run_single bugfix |
| `backend/app/services/knowledge/graph_ids.py` | SHA-256 node_id/edge_id (new file) |
| `backend/app/services/knowledge/embeddings.py` | CAST fix for vector inserts |
| `backend/app/services/knowledge/repo_manifest.py` | SHA-256 manifest + role classification (new) |
| `backend/app/services/knowledge/incremental_graph.py` | Incremental sync + import centrality (new) |
| `backend/app/services/knowledge/architecture_map.py` | Architecture analysis (new) |
| `backend/app/services/onboarding/pipeline.py` | Sync graph builder, sync embeddings, clone_path threading |
| `backend/app/services/agent/tools.py` | Reduced tool list, added list_prs/explain_architecture/trace_issue |
| `backend/app/services/agent/confidence.py` | Confidence decay with half-life (new) |
| `backend/app/services/agent/auto_sync.py` | Webhook + polling sync engine (new) |
| `backend/app/services/agent/pr_reviewer.py` | PR code reviewer (new) |
| `backend/app/services/agent/blame_tracer.py` | Git blame + call graph tracer (new) |
| `backend/app/services/agent/cost_tracker.py` | Cost + audit logging (new) |
| `backend/app/services/reporting/digest.py` | Weekly digest generator (new) |
| `backend/app/services/reporting/docs_generator.py` | Auto docs from KG (new) |
| `backend/app/services/integrations/slack_bot.py` | Slack integration (new) |
| `backend/app/api/reporting.py` | Reports/digest/docs/sync endpoints (new) |
| `backend/app/api/webhooks.py` | Auto-sync webhook trigger |
| `backend/app/main.py` | Auto-sync polling at startup |
| `backend/app/config.py` | Auto-sync, digest settings |
| `backend/app/utils/git.py` | Bare clone support, remote handling |
| `frontend/src/app/chat/page.tsx` | Tool chips hidden, history sent, clear button |
| `docker-compose.yml` | Prometheus/Grafana to monitoring profile |

## Git History
```
947f9c2 Fix NameError crash in system prompt (undefined {repo})
76c40b4 Fix agent behavior: stop when found, batch edits on 'yes', plain tool notes
ec433a1 Fix list_prs: extract owner/repo from github_url, batch all repos
3c8ea0d Make agent smarter: capability-aware prompt, PR listing, hidden tool chips
0f216ae Fix critical pipeline + chat bugs
44b95a5 Add 7 major features: auto-sync, PR review, blame tracer, digest, docs generator, Slack bot
8cc0020 Fix 14 bugs — graph ID consistency, cost tracking, pipeline errors, git safety, SQL injection
d62e914 Fix syntax error in empty-result yield string
a0ec420 Reduce tool list to 15 core tools
```
