# TeammateX — Remaining work

_What's left. Shipped work lives in git history / commit messages._

## Next up
- **Research whim.run.** Review the whim.run website, its offering + docs, and assess
  what we could bring into TeammateX (capabilities, integrations, UX/agent patterns).
  Deliver a short writeup + concrete candidate ideas.

## Honest-UI follow-ups (these Settings controls are currently disabled with a note)
- **Updates**: config-driven auto-sync interval + GitHub-webhook triggers.
- **Slack / Jira**: wire credential save + actually use them.

## Citations / evals follow-ups (deferred from the as-built design)
- **Extend citation sources**: `grep_search`, `glob_search`, `find_dependents`,
  `find_dependencies`, `get_architecture` are NOT yet extracted as citation sources
  (their result shapes weren't pinned). Today this only ever *under*-cites (never wrong);
  extend `agent/citations.py` when the shapes are confirmed.
- **Multi-repo citations**: chat is single-repo today, so a file path alone is an
  unambiguous Source key. Add `repo` to the Source + dedup key when chat goes multi-repo.
- **Eval live mode**: the eval CLI runs in-process; a `--instance <url>` live-mode flag
  is not yet implemented. The engine is instance-agnostic (`run_eval(db, embedder, …)`),
  so it's a small add when a live golden set is authored.

## Known issues / tech debt
- **Rotate credentials**: the leaked DeepSeek key + GitHub PAT are still in git history
  (user action — see `SECURITY.md`). The available GitHub PAT is read-only (pushes 403).
- **Legacy embeddings have NULL `repo_id`**: rows written before repo-scoping aren't
  attributable to a repo (relative paths), so they're invisible to scoped search and
  the per-repo DELETE cleanup. A one-time re-onboard of existing repos repopulates them.
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
