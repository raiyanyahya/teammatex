# TeammateX — Remaining work

_What's left. Shipped work lives in git history / commit messages._

## Next up
- **Research whim.run.** Review the whim.run website, its offering + docs, and assess
  what we could bring into TeammateX (capabilities, integrations, UX/agent patterns).
  Deliver a short writeup + concrete candidate ideas.

## Honest-UI follow-ups (these Settings controls are currently disabled with a note)
- **Persona**: read from `app_config` in `runtime._get_persona_prompt` (settings fallback)
  so the picker actually changes the agent.
- **Updates**: config-driven auto-sync interval + GitHub-webhook triggers.
- **Permissions**: enforce them (the `permissions` model exists but nothing checks it).
- **Slack / Jira**: wire credential save + actually use them.

## Known issues / tech debt
- **Rotate credentials**: the leaked DeepSeek key + GitHub PAT are still in git history
  (user action — see `SECURITY.md`). The available GitHub PAT is read-only (pushes 403).
- **Embeddings aren't repo-scoped**: `code_embeddings` has no `repo_id`, so
  `DELETE /api/repos/{id}` can't clean a single repo's vectors. The same gap breaks
  semantic search's repo filter — `ce.file_path LIKE 'repos/{id}/%'` matches nothing
  (stored paths are repo-relative, e.g. `src/main.py`), and identical relative paths
  across repos collide on the md5 `_chunk_id`. Fix = add `repo_id` (column + migration),
  thread it through `embed_and_store`, filter/delete by it, key `_chunk_id` on it.
- `pr_reviewer` + Slack: exercise end-to-end with live inputs.
- (optional) Add pytest to the dev image so the suite runs without a manual pip install.

## Reference / gotchas
- DeepSeek-only via DB `app_config.llm_config` (`.env` keys empty). Provider/model
  metadata: `GET /api/config/llm/providers`.
- Code is baked into images: `docker cp` + `docker compose restart` for quick changes,
  `docker compose build api worker frontend` to persist. Tests run in the api container
  (`pip install pytest pytest-asyncio` first — the prod image omits them).
- Neo4j: `change-me-neo4j`. Postgres: `teammatex`/`teammatex`. Login:
  `admin@teammatex.local` (password is the first-run-generated one, not "test").
