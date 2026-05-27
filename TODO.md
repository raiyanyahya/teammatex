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
