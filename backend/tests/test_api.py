"""Test the API endpoints against a real async Postgres test database.

The app uses async SQLAlchemy + pgvector + JSONB, so endpoints are exercised
through httpx.AsyncClient + ASGITransport (in-process, one event loop) with
get_db overridden to a per-test transaction that rolls back. The `api_client`
fixture lives in conftest.py. The whole module shares a session-scoped event
loop so the async singletons (Neo4j driver, asyncpg engine) stay on one loop.
"""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestHealthEndpoint:
    async def test_health_returns_ok(self, api_client):
        response = await api_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "teammatex-api"


class TestAgentEndpoints:
    async def test_list_tools(self, api_client):
        response = await api_client.get("/api/agent/tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) >= 20

    async def test_validate_code_pass(self, api_client):
        response = await api_client.post("/api/agent/validate", json={
            "code": "def hello(): return 'world'",
            "file_path": "test.py",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["passed"] is True

    async def test_validate_code_fail(self, api_client):
        response = await api_client.post("/api/agent/validate", json={
            "code": 'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"',
            "file_path": "secrets.py",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["passed"] is False

    async def test_plan_endpoint_accepts_request(self, api_client):
        response = await api_client.post("/api/agent/plan", json={
            "task": "Add rate limiting to login endpoint",
            "repo_id": None,
        })
        assert response.status_code in (200, 500)
        assert "plan" in response.json()

    async def test_tool_execute_returns_error_for_bad_tool(self, api_client):
        response = await api_client.post("/api/agent/tool", json={
            "tool_name": "nonexistent_tool",
            "arguments": {},
        })
        assert response.status_code == 400


class TestKnowledgeEndpoints:
    async def test_get_architecture_no_repo(self, api_client):
        response = await api_client.get("/api/knowledge/graph/architecture", params={"repo_id": "nonexistent"})
        assert response.status_code == 200

    async def test_graph_search(self, api_client):
        response = await api_client.get("/api/knowledge/graph/search", params={"query": "auth"})
        assert response.status_code == 200
        assert "results" in response.json()

    async def test_create_note(self, api_client):
        response = await api_client.post("/api/knowledge/notes", json={
            "title": "Test Note",
            "content": "Test content for validation",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Note"

    async def test_list_notes(self, api_client):
        await api_client.post("/api/knowledge/notes", json={"title": "List test", "content": "Content"})
        response = await api_client.get("/api/knowledge/notes")
        assert response.status_code == 200
        assert "notes" in response.json()


class TestRepoEndpoints:
    async def test_list_repos(self, api_client):
        response = await api_client.get("/api/repos")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_add_repo_invalid_url(self, api_client):
        # A bare token with no "/" is treated as an org/user import, which
        # needs a GitHub token — so an unparseable URL is correctly rejected.
        response = await api_client.post("/api/repos", json={
            "github_url": "not-a-valid-url",
        })
        assert response.status_code == 400

    async def test_get_onboarding_status_nonexistent(self, api_client):
        response = await api_client.get("/api/repos/nonexistent-id/onboarding")
        assert response.status_code == 200

    async def test_duplicate_repo(self, api_client):
        payload = {"github_url": "https://github.com/dup/test-repo"}
        await api_client.post("/api/repos", json=payload)
        response = await api_client.post("/api/repos", json=payload)
        assert response.status_code == 409


class TestIntegrationEndpoints:
    async def test_list_integrations(self, api_client):
        response = await api_client.get("/api/integrations")
        assert response.status_code == 200
        assert "integrations" in response.json()

    async def test_integration_status(self, api_client):
        response = await api_client.get("/api/integrations/status")
        assert response.status_code == 200
        data = response.json()
        assert "github" in data
        assert "jira" in data
        assert "slack" in data

    async def test_github_repos_not_configured(self, api_client):
        response = await api_client.get("/api/integrations/github/repos")
        assert response.status_code == 400

    async def test_jira_not_configured(self, api_client):
        response = await api_client.get("/api/integrations/jira/projects")
        assert response.status_code == 400

    async def test_slack_not_configured(self, api_client):
        response = await api_client.get("/api/integrations/slack/channels")
        assert response.status_code == 400


class TestPluginsEndpoints:
    async def test_list_plugins(self, api_client):
        response = await api_client.get("/api/plugins")
        assert response.status_code == 200
        assert "plugins" in response.json()

    async def test_discover_plugins(self, api_client):
        response = await api_client.post("/api/plugins/discover")
        assert response.status_code == 200

    async def test_list_plugin_tools(self, api_client):
        response = await api_client.get("/api/plugins/tools")
        assert response.status_code == 200

    async def test_marketplace_search(self, api_client):
        response = await api_client.get("/api/plugins/marketplace/search", params={"query": ""})
        assert response.status_code == 200

    async def test_nonexistent_plugin_reload(self, api_client):
        response = await api_client.post("/api/plugins/nonexistent/reload")
        assert response.status_code == 404


class TestFeaturesEndpoints:
    async def test_generate_standup(self, api_client):
        response = await api_client.post("/api/features/standup")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "date" in data
        assert "yesterday" in data

    async def test_standup_get_buckets_prs_tasks_and_pending_blockers(self, api_client, api_db):
        """GET /api/features/standup returns recent PRs, active tasks, and only
        the *pending* blockers as structured arrays for the in-app standup page."""
        from app.models.repo import Repo
        from app.models.pr import PR
        from app.models.task import Task
        from app.models.blocked import BlockedTask

        repo = Repo(github_url="https://example.com/r.git", local_name="r")
        api_db.add(repo)
        await api_db.flush()

        task = Task(title="Wire up metrics", status="in_progress", priority="high")
        api_db.add(task)
        await api_db.flush()

        api_db.add(PR(repo_id=repo.id, branch="feat/rl", title="Add rate limiting", status="open"))
        api_db.add(BlockedTask(task_id=task.id, question="Which OAuth provider?", status="pending"))
        api_db.add(BlockedTask(task_id=task.id, question="Already answered", status="answered"))
        await api_db.flush()

        response = await api_client.get("/api/features/standup")
        assert response.status_code == 200
        data = response.json()

        assert any(p["title"] == "Add rate limiting" for p in data["prs"])
        assert any(t["title"] == "Wire up metrics" for t in data["tasks"])

        questions = [b["question"] for b in data["blockers_list"]]
        assert "Which OAuth provider?" in questions
        assert "Already answered" not in questions

    async def test_generate_module_docs(self, api_client):
        response = await api_client.post("/api/features/docs/module", json={
            "module_name": "auth",
            "code_summary": "Handles user authentication",
            "entities": [],
        })
        assert response.status_code in (200, 500)

    async def test_generate_release_notes(self, api_client):
        response = await api_client.post("/api/features/release-notes", json={
            "repo_name": "test-repo",
            "commits": [{"hash": "abc123", "message": "Add feature X"}],
        })
        assert response.status_code in (200, 500)


class TestAPIRegistryEndpoints:
    async def test_list_registry(self, api_client):
        response = await api_client.get("/api/api-registry")
        assert response.status_code == 200

    async def test_add_entry(self, api_client):
        response = await api_client.post("/api/api-registry", json={
            "domain": "api.example.com",
            "description": "Test API",
            "allowed_methods": ["GET"],
            "allowed_paths": ["/*"],
        })
        assert response.status_code == 201

    async def test_check_url_not_registered(self, api_client):
        response = await api_client.post("/api/api-registry/check", json={
            "url": "https://unknown.example.com/api",
            "method": "GET",
        })
        assert response.status_code == 200
        assert response.json()["allowed"] is False

    async def test_check_url_registered(self, api_client):
        await api_client.post("/api/api-registry", json={
            "domain": "check.example.com",
            "allowed_methods": ["GET"],
            "allowed_paths": ["/*"],
        })
        response = await api_client.post("/api/api-registry/check", json={
            "url": "https://check.example.com/data",
            "method": "GET",
        })
        assert response.status_code == 200
        assert response.json()["allowed"] is True


class TestWebhookEndpoints:
    async def test_slack_url_verification(self, api_client):
        response = await api_client.post("/api/webhooks/slack", json={
            "type": "url_verification",
            "challenge": "test-challenge-123",
        })
        assert response.status_code == 200
        assert response.json()["challenge"] == "test-challenge-123"

    async def test_slack_event_callback(self, api_client):
        response = await api_client.post("/api/webhooks/slack", json={
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "text": "Hello teammate!",
                "channel": "C123",
                "user": "U456",
            },
        })
        assert response.status_code == 200

    async def test_github_webhook_no_signature_handles(self, api_client):
        response = await api_client.post(
            "/api/webhooks/github",
            json={"action": "opened", "pull_request": {"number": 1}},
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert response.status_code == 200

    async def test_jira_webhook(self, api_client):
        response = await api_client.post("/api/webhooks/jira", json={
            "webhookEvent": "jira:issue_updated",
            "issue": {"key": "PROJ-1", "fields": {"summary": "Test"}},
        })
        assert response.status_code == 200
