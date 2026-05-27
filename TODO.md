# TeammateX — Remaining work

_What's left. Shipped work lives in git history / commit messages._

## Next up
- **WS4 — Team from the graph (read-only).** Replace the Team page's login-user list
  and the register-with-hardcoded-password form with the contributors the knowledge
  graph already profiles. Backend: `KnowledgeGraph.list_contributors()` +
  `GET /api/knowledge/contributors` (name, email, files owned, repos, languages).
  Frontend: read-only contributor list; drop the account-creation form.
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
- **Secret leak**: `GET /api/config` returns the raw `llm_config.api_key` to any
  authenticated client — mask/omit secrets server-side.
- **Rotate credentials**: the leaked DeepSeek key + GitHub PAT are still in git history
  (user action — see `SECURITY.md`). The available GitHub PAT is read-only (pushes 403).
- `add_repo` org-import path enqueues onboarding before commit (same race fixed in
  `/repos/bulk`).
- `DELETE /api/repos/{id}` leaves the cloned checkout (`/data/repos`) + pgvector
  embeddings — add a cleanup pass.
- `retryPipeline`'s `setInterval` isn't cleared on unmount (onboarding page).
- `logs/page.tsx`: `react-hooks/exhaustive-deps` lint warning.
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
