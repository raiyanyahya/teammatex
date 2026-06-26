# Contributing to TeammateX

Thanks for taking the time to contribute! 🦾 TeammateX is in **alpha**, so this
is exactly the stage where issues, ideas, and pull requests have the most
impact. This guide gets you from clone to merged PR.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Ways to contribute

- 🐛 **Report a bug** — open a [bug report](https://github.com/raiyanyahya/teammatex/issues/new/choose).
- 💡 **Suggest a feature** — open a [feature request](https://github.com/raiyanyahya/teammatex/issues/new/choose).
- 📖 **Improve docs** — the README, this guide, inline docstrings.
- 🔧 **Fix or build** — grab an open issue (look for `good first issue`) or propose something.
- 🔒 **Report a vulnerability** — please **don't** open a public issue; see [SECURITY.md](SECURITY.md).

If your change is large, **open an issue first** to discuss the approach before
writing a lot of code — it saves everyone a round of rework.

---

## Development setup

You need **Docker + Docker Compose v2**, ~6 GB free RAM, and one LLM API key
(or a local Ollama model). The whole stack runs in containers.

```bash
git clone https://github.com/raiyanyahya/teammatex.git
cd teammatex
cp .env.example .env          # set TEAMMATEX_SECRET_KEY + one LLM key

# Full stack with hot-reload helpers
./scripts/dev.sh
# or
docker compose up -d --build
```

Working on one side only:

```bash
# Backend (FastAPI, Python 3.12, Poetry)
cd backend && poetry install && poetry run uvicorn app.main:app --reload

# Frontend (Next.js 14, Node 20)
cd frontend && npm install && npm run dev
```

> **Dev loop note:** application code is baked into the image (no bind mount).
> For a quick change in a running stack: `docker cp <file> teammatex-api-1:/app/...`
> then `docker compose restart api`. To persist: `docker compose build api worker frontend`.

---

## Before you open a PR

Run the same checks CI runs, so the pipeline is green on the first push.

### Backend

```bash
cd backend
poetry run ruff check .          # lint
poetry run black --check .       # format
poetry run mypy app/             # types
poetry run pytest -q             # tests
```

Tests run against a real ephemeral Postgres + Neo4j with per-test transaction
rollback. In a running stack you can also do:

```bash
docker compose exec api pip install -q pytest pytest-asyncio
docker compose exec api python -m pytest -q
```

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

A `.pre-commit-config.yaml` is provided — `pre-commit install` to run the
fast checks automatically on every commit.

---

## Coding conventions

- **Match the surrounding code.** Naming, comment density, and idiom should look
  like the file you're editing.
- **Comments explain *why*, not *what*.** The codebase favors short, purposeful
  docstrings on non-obvious functions over line-by-line narration.
- **Keep changes focused.** One logical change per PR; avoid drive-by reformatting.
- **Add/adjust tests** for any behavior change. New tools, endpoints, or services
  should ship with coverage.
- **Security-sensitive paths** (auth, the agent's tools, webhooks, the plugin
  sandbox) deserve extra care and a clear PR description of the threat model.

### Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short summary

Longer body explaining the why, if needed.
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`.
Examples:

```
fix(security): block SSRF in agent http_request tool
feat(chat): add per-conversation export to Markdown
docs(readme): document the cost budget guardrail
```

---

## Pull request process

1. Fork the repo and create a branch from `master` (e.g. `feat/cost-budget`).
2. Make your change with tests and green local checks.
3. Open a PR against `master`, filling in the PR template.
4. Link any related issue (`Closes #123`).
5. A maintainer reviews; address feedback by pushing follow-up commits.
6. Once CI is green and the review is approved, a maintainer merges.

Small, well-described PRs get reviewed fastest. Thank you for helping make
TeammateX better! 💛
