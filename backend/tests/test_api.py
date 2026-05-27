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

    async def test_list_contributors(self, api_client):
        response = await api_client.get("/api/knowledge/contributors")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["contributors"], list)
        assert data["count"] == len(data["contributors"])


class TestKnowledgeGraphContributors:
    """KnowledgeGraph.list_contributors aggregates OWNS edges into a per-person
    profile (files owned, repos, languages). Seeds throwaway nodes in Neo4j and
    cleans them up — Neo4j has no per-test rollback like the Postgres fixtures."""

    async def test_list_contributors_aggregates_ownership(self):
        from app.services.knowledge.graph import KnowledgeGraph

        g = KnowledgeGraph()
        repo_id = "ws4-test-repo"
        email = "ws4-contributor@example.com"
        try:
            await g.ensure_repo_node(repo_id, "ws4-repo")
            await g.ensure_file_node(repo_id, "a.py", "python", 10)
            await g.ensure_file_node(repo_id, "b.js", "javascript", 20)
            await g.ensure_file_node(repo_id, "LICENSE", "", 5)  # no detected language
            await g.ensure_contributor_node(email, "WS4 Tester")
            await g.add_ownership(email, repo_id, "a.py")
            await g.add_ownership(email, repo_id, "b.js")
            await g.add_ownership(email, repo_id, "LICENSE")

            contributors = await g.list_contributors()
            mine = next(c for c in contributors if c["email"] == email)

            assert mine["name"] == "WS4 Tester"
            assert mine["files_owned"] == 3
            assert mine["repos"] == ["ws4-repo"]
            # the empty-language file counts toward files_owned but must not
            # surface as a blank language badge.
            assert set(mine["languages"]) == {"python", "javascript"}
        finally:
            await g.run("MATCH (n) WHERE n.repo_id = $rid DETACH DELETE n", rid=repo_id)
            await g.run("MATCH (c:Contributor {email: $e}) DETACH DELETE c", e=email)


class TestConfigEndpoints:
    """GET /api/config and /api/config/{key} must never echo stored secrets
    (llm api_key, github token, etc.) back to a client — only a masked marker,
    while leaving non-secret fields and the set/unset signal intact."""

    async def test_get_config_by_key_masks_api_key(self, api_client, api_db):
        from app.models.app_config import AppConfig

        api_db.add(AppConfig(key="llm_config", value={
            "provider": "deepseek", "model": "deepseek-chat", "api_key": "sk-supersecret123",
        }))
        await api_db.flush()

        r = await api_client.get("/api/config/llm_config")
        assert r.status_code == 200
        value = r.json()["value"]
        assert value["provider"] == "deepseek"      # non-secret preserved
        assert value["model"] == "deepseek-chat"
        assert value["api_key"] != "sk-supersecret123"
        assert "supersecret" not in str(value)

    async def test_get_all_config_masks_secrets(self, api_client, api_db):
        from app.models.app_config import AppConfig

        api_db.add(AppConfig(key="llm_config", value={"provider": "deepseek", "api_key": "sk-leakme"}))
        api_db.add(AppConfig(key="github_token", value={"token": "ghp_leakme"}))
        await api_db.flush()

        r = await api_client.get("/api/config")
        assert r.status_code == 200
        body = str(r.json())
        assert "sk-leakme" not in body
        assert "ghp_leakme" not in body

    async def test_set_config_preserves_masked_secret(self, api_client, api_db):
        """A client that saves the redacted mask back (e.g. changed the model but
        left the key field untouched) must not clobber the real stored secret."""
        from sqlalchemy import select
        from app.models.app_config import AppConfig

        api_db.add(AppConfig(key="llm_config", value={
            "provider": "deepseek", "model": "deepseek-chat", "api_key": "sk-original",
        }))
        await api_db.flush()

        r = await api_client.put("/api/config/llm_config", json={"key": "llm_config", "value": {
            "provider": "deepseek", "model": "deepseek-reasoner", "api_key": "********",
        }})
        assert r.status_code == 200

        row = (await api_db.execute(select(AppConfig).where(AppConfig.key == "llm_config"))).scalar_one()
        assert row.value["api_key"] == "sk-original"        # real key preserved
        assert row.value["model"] == "deepseek-reasoner"     # non-secret change applied


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

    async def test_bulk_add_creates_new_and_skips_existing(self, api_client):
        """POST /api/repos/bulk onboards every new url and skips ones already added."""
        await api_client.post("/api/repos", json={"github_url": "https://github.com/acme/already.git"})

        response = await api_client.post("/api/repos/bulk", json={"github_urls": [
            "https://github.com/acme/already.git",     # duplicate -> skipped
            "https://github.com/acme/fresh-one.git",   # new -> added
            "https://github.com/acme/fresh-two.git",   # new -> added
        ]})
        assert response.status_code in (200, 201)
        data = response.json()

        added_urls = {a["url"] for a in data["added"]}
        assert added_urls == {
            "https://github.com/acme/fresh-one.git",
            "https://github.com/acme/fresh-two.git",
        }
        assert {a["local_name"] for a in data["added"]} == {"fresh-one", "fresh-two"}
        assert all(a.get("repo_id") for a in data["added"])
        assert "https://github.com/acme/already.git" in data["skipped"]

    async def test_delete_repo_removes_it_and_children(self, api_client, api_db):
        from app.models.pr import PR

        r = await api_client.post("/api/repos", json={"github_url": "https://github.com/del/me.git"})
        rid = r.json()["repo_id"]
        api_db.add(PR(repo_id=rid, branch="b", title="t", status="open"))  # child FK row
        await api_db.flush()

        resp = await api_client.delete(f"/api/repos/{rid}")
        assert resp.status_code == 200

        repos = (await api_client.get("/api/repos")).json()
        assert all(x["id"] != rid for x in repos)

    async def test_delete_nonexistent_repo_404(self, api_client):
        resp = await api_client.delete("/api/repos/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_delete_repo_removes_cloned_checkout(self, api_client, tmp_path, monkeypatch):
        """Deleting a repo also removes its cloned checkout from disk, not just
        its DB rows."""
        from app.services.agent import environment
        monkeypatch.setattr(environment, "REPOS_ROOT", str(tmp_path))

        r = await api_client.post("/api/repos", json={"github_url": "https://github.com/del/checkout.git"})
        rid = r.json()["repo_id"]
        local_name = r.json()["local_name"]

        checkout = tmp_path / local_name
        checkout.mkdir()
        (checkout / "main.py").write_text("print('hi')")

        resp = await api_client.delete(f"/api/repos/{rid}")
        assert resp.status_code == 200
        assert not checkout.exists()

    async def test_delete_repo_removes_embeddings(self, api_client, api_db):
        """Deleting a repo purges its pgvector rows (scoped by repo_id)."""
        from sqlalchemy import text

        r = await api_client.post("/api/repos", json={"github_url": "https://github.com/del/emb.git"})
        rid = r.json()["repo_id"]
        await api_db.execute(
            text("INSERT INTO code_embeddings (id, repo_id, text, file_path, start_line, end_line) "
                 "VALUES (:id, :rid, 'x', 'src/a.py', 1, 2)"),
            {"id": "e" * 32, "rid": rid},
        )
        await api_db.flush()

        resp = await api_client.delete(f"/api/repos/{rid}")
        assert resp.status_code == 200
        remaining = (await api_db.execute(
            text("SELECT count(*) FROM code_embeddings WHERE repo_id = :rid"), {"rid": rid}
        )).scalar()
        assert remaining == 0


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

    async def test_github_repo_mapping_includes_fork_and_archived(self):
        """The /user/repos mapping surfaces fork + archived so the onboarding
        selector can apply its smart default (uncheck forks/archived)."""
        from app.api.integrations import _map_gh_repo

        mapped = _map_gh_repo({
            "full_name": "acme/widget", "clone_url": "https://github.com/acme/widget.git",
            "default_branch": "main", "private": True, "language": "Python",
            "fork": True, "archived": False,
        })
        assert mapped["name"] == "acme/widget"
        assert mapped["url"] == "https://github.com/acme/widget.git"
        assert mapped["fork"] is True
        assert mapped["archived"] is False

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
