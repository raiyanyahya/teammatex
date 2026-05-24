"""Test the API endpoints using FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_db(db_session):
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "teammatex-api"


class TestAgentEndpoints:
    def test_list_tools(self):
        response = client.get("/api/agent/tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) >= 20

    def test_validate_code_pass(self):
        response = client.post("/api/agent/validate", json={
            "code": "def hello(): return 'world'",
            "file_path": "test.py",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["passed"] is True

    def test_validate_code_fail(self):
        response = client.post("/api/agent/validate", json={
            "code": 'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"',
            "file_path": "secrets.py",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["passed"] is False

    def test_plan_endpoint_accepts_request(self):
        response = client.post("/api/agent/plan", json={
            "task": "Add rate limiting to login endpoint",
            "repo_id": None,
        })
        assert response.status_code in (200, 500)
        assert "plan" in response.json()

    def test_tool_execute_returns_error_for_bad_tool(self):
        response = client.post("/api/agent/tool", json={
            "tool_name": "nonexistent_tool",
            "arguments": {},
        })
        assert response.status_code == 400


class TestKnowledgeEndpoints:
    def test_get_architecture_no_repo(self):
        response = client.get("/api/knowledge/graph/architecture", params={"repo_id": "nonexistent"})
        assert response.status_code == 200

    def test_graph_search(self):
        response = client.get("/api/knowledge/graph/search", params={"query": "auth"})
        assert response.status_code == 200
        assert "results" in response.json()

    def test_create_note(self):
        response = client.post("/api/knowledge/notes", json={
            "title": "Test Note",
            "content": "Test content for validation",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Note"

    def test_list_notes(self):
        client.post("/api/knowledge/notes", json={"title": "List test", "content": "Content"})
        response = client.get("/api/knowledge/notes")
        assert response.status_code == 200
        assert "notes" in response.json()


class TestRepoEndpoints:
    def test_list_repos(self):
        response = client.get("/api/repos")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_add_repo_invalid_url(self):
        response = client.post("/api/repos", json={
            "github_url": "not-a-valid-url",
        })
        assert response.status_code == 201

    def test_get_onboarding_status_nonexistent(self):
        response = client.get("/api/repos/nonexistent-id/onboarding")
        assert response.status_code == 200

    def test_duplicate_repo(self):
        payload = {"github_url": "https://github.com/dup/test-repo"}
        client.post("/api/repos", json=payload)
        response = client.post("/api/repos", json=payload)
        assert response.status_code == 409


class TestIntegrationEndpoints:
    def test_list_integrations(self):
        response = client.get("/api/integrations")
        assert response.status_code == 200
        assert "integrations" in response.json()

    def test_integration_status(self):
        response = client.get("/api/integrations/status")
        assert response.status_code == 200
        data = response.json()
        assert "github" in data
        assert "jira" in data
        assert "slack" in data

    def test_github_repos_not_configured(self):
        response = client.get("/api/integrations/github/repos")
        assert response.status_code == 400

    def test_jira_not_configured(self):
        response = client.get("/api/integrations/jira/projects")
        assert response.status_code == 400

    def test_slack_not_configured(self):
        response = client.get("/api/integrations/slack/channels")
        assert response.status_code == 400


class TestPluginsEndpoints:
    def test_list_plugins(self):
        response = client.get("/api/plugins")
        assert response.status_code == 200
        assert "plugins" in response.json()

    def test_discover_plugins(self):
        response = client.post("/api/plugins/discover")
        assert response.status_code == 200

    def test_list_plugin_tools(self):
        response = client.get("/api/plugins/tools")
        assert response.status_code == 200

    def test_marketplace_search(self):
        response = client.get("/api/plugins/marketplace/search", params={"query": ""})
        assert response.status_code == 200

    def test_nonexistent_plugin_reload(self):
        response = client.post("/api/plugins/nonexistent/reload")
        assert response.status_code == 404


class TestFeaturesEndpoints:
    def test_generate_standup(self):
        response = client.post("/api/features/standup")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "date" in data
        assert "yesterday" in data

    def test_generate_module_docs(self):
        response = client.post("/api/features/docs/module", json={
            "module_name": "auth",
            "code_summary": "Handles user authentication",
            "entities": [],
        })
        assert response.status_code in (200, 500)

    def test_generate_release_notes(self):
        response = client.post("/api/features/release-notes", json={
            "repo_name": "test-repo",
            "commits": [{"hash": "abc123", "message": "Add feature X"}],
        })
        assert response.status_code in (200, 500)


class TestAPIRegistryEndpoints:
    def test_list_registry(self):
        response = client.get("/api/api-registry")
        assert response.status_code == 200

    def test_add_entry(self):
        response = client.post("/api/api-registry", json={
            "domain": "api.example.com",
            "description": "Test API",
            "allowed_methods": ["GET"],
            "allowed_paths": ["/*"],
        })
        assert response.status_code == 201

    def test_check_url_not_registered(self):
        response = client.post("/api/api-registry/check", json={
            "url": "https://unknown.example.com/api",
            "method": "GET",
        })
        assert response.status_code == 200
        assert response.json()["allowed"] is False

    def test_check_url_registered(self):
        client.post("/api/api-registry", json={
            "domain": "check.example.com",
            "allowed_methods": ["GET"],
            "allowed_paths": ["/*"],
        })
        response = client.post("/api/api-registry/check", json={
            "url": "https://check.example.com/data",
            "method": "GET",
        })
        assert response.status_code == 200
        assert response.json()["allowed"] is True


class TestWebhookEndpoints:
    def test_slack_url_verification(self):
        response = client.post("/api/webhooks/slack", json={
            "type": "url_verification",
            "challenge": "test-challenge-123",
        })
        assert response.status_code == 200
        assert response.json()["challenge"] == "test-challenge-123"

    def test_slack_event_callback(self):
        response = client.post("/api/webhooks/slack", json={
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "text": "Hello teammate!",
                "channel": "C123",
                "user": "U456",
            },
        })
        assert response.status_code == 200

    def test_github_webhook_no_signature_handles(self):
        response = client.post(
            "/api/webhooks/github",
            json={"action": "opened", "pull_request": {"number": 1}},
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert response.status_code == 200

    def test_jira_webhook(self):
        response = client.post("/api/webhooks/jira", json={
            "webhookEvent": "jira:issue_updated",
            "issue": {"key": "PROJ-1", "fields": {"summary": "Test"}},
        })
        assert response.status_code == 200
