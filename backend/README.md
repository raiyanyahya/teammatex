# TeammateX Backend

FastAPI backend for TeammateX — the AI teammate that learns your codebase and
works alongside your team.

## Development

```bash
poetry install
poetry run uvicorn app.main:app --reload
```

Run the tests (Postgres with the pgvector extension must be reachable; see
`tests/conftest.py` for the connection defaults):

```bash
poetry run pytest
```

See the [repository README](../README.md) for full setup, including the
docker-compose stack with Postgres, Neo4j and Redis.
