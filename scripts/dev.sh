#!/usr/bin/env bash
set -euo pipefail

echo "=== TeammateX Dev Environment ==="

# Initialize .env if missing
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — review and edit it"
fi

# Start infrastructure services
docker compose up -d postgres neo4j redis

echo "Waiting for services..."
until docker compose exec -T postgres pg_isready -U teammatex > /dev/null 2>&1; do sleep 1; done
echo "Postgres ready"
until docker compose exec -T redis redis-cli ping > /dev/null 2>&1; do sleep 1; done
echo "Redis ready"

# Backend
cd backend
if [ ! -d .venv ]; then
  python3.12 -m venv .venv
fi
source .venv/bin/activate
pip install poetry
poetry install
echo "Running migrations..."
alembic upgrade head
echo "Starting API..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Frontend
cd frontend
if [ ! -d node_modules ]; then
  npm install
fi
echo "Starting frontend..."
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "API:      http://localhost:8000/api/health"
echo "Frontend: http://localhost:3000"
echo ""

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
