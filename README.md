# TeammateX

A self-hosted AI teammate that onboards itself into your team, learns your entire codebase and history, builds a knowledge graph, and participates as a full team member — answering questions, writing code, creating PRs, and integrating with GitHub, Jira, and Slack.

## Quickstart

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your API keys

# Launch
docker compose up -d

# Open https://localhost/setup
```

## Architecture

- **Backend**: FastAPI + Celery + PostgreSQL/pgvector + Neo4j + Redis
- **Frontend**: Next.js 14 + Tailwind + shadcn/ui
- **LLM**: LiteLLM (OpenAI, Anthropic, DeepSeek, Ollama, Groq, Together)
- **Infra**: Docker Compose (Caddy, Prometheus, Grafana)

## Development

```bash
# Backend
cd backend && poetry install && poetry run uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev

# Full stack
./scripts/dev.sh
```
