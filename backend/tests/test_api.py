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

    async def test_health_includes_uptime_seconds(self, api_client):
        """Sidebar reads `uptime_seconds` from /api/health to render `uptime`.
        Must be a non-negative integer so the formatter can render m/h/d."""
        response = await api_client.get("/api/health")
        data = response.json()
        assert isinstance(data["uptime_seconds"], int)
        assert data["uptime_seconds"] >= 0


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

    async def test_list_repos_includes_health_fields(self, api_client, api_db):
        """The dashboard Repository-health card reads `files`/`open_prs`/`health`
        from /api/repos. Each row must carry the four computed integers so the
        card renders real numbers instead of falling back to mocked content."""
        from app.models.repo import Repo
        api_db.add(Repo(github_url="https://x/y", local_name="health-test"))
        await api_db.flush()

        response = await api_client.get("/api/repos")
        assert response.status_code == 200
        body = response.json()
        row = next(r for r in body if r["local_name"] == "health-test")
        for key in ("files", "open_prs", "onboarding_pct", "health"):
            assert key in row, f"missing {key}"
            assert isinstance(row[key], int)
        assert 0 <= row["health"] <= 100
        assert 0 <= row["onboarding_pct"] <= 100

    async def test_concepts_skip_third_party_imports(self, api_client):
        """The endpoint must NOT surface raw Module nodes — those include every
        imported symbol the parser saw (stdlib `os`/`fs`, framework symbols
        like `BrowserWindow`, destructure-noise like `{`). Knowledge cards
        come from source-tree subsystems + curated Notes only."""
        response = await api_client.get("/api/knowledge/concepts?limit=60")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["concepts"], list)
        assert data["count"] == len(data["concepts"])
        cats = {c["cat"] for c in data["concepts"]}
        # Whatever shows up must be either a real source surface or a note.
        assert cats.issubset({"subsystem", "note"})
        # Common framework/stdlib names that previously leaked through.
        names = {c["name"] for c in data["concepts"]}
        for noise in ("os", "fs", "path", "BrowserWindow", "ipcMain", "dialog", "{"):
            assert noise not in names, f"{noise!r} should not appear as a concept"

    async def test_graph_stats_returns_concept_counts(self, api_client):
        response = await api_client.get("/api/knowledge/graph/stats")
        assert response.status_code == 200
        data = response.json()
        for key in ("files", "modules", "functions", "classes", "concepts"):
            assert key in data
            assert isinstance(data[key], int)
        assert data["concepts"] == data["files"] + data["modules"] + data["functions"] + data["classes"]


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

    async def test_list_contributors_merges_same_person_across_emails(self):
        """One human often commits under several git emails (work vs personal),
        which the pipeline stores as separate Contributor nodes. list_contributors
        must surface ONE row per person — keyed on name — counting each owned file
        once across all of that person's nodes, so the Team page shows no dupes
        and no inflated file totals."""
        from app.services.knowledge.graph import KnowledgeGraph

        g = KnowledgeGraph()
        repo_id = "dedup-test-repo"
        email_a = "dup@example.com"
        email_b = "dup-alt@example.com"
        try:
            await g.ensure_repo_node(repo_id, "dedup-repo")
            await g.ensure_file_node(repo_id, "a.py", "python", 10)
            await g.ensure_file_node(repo_id, "b.py", "python", 20)

            # Same person "Dup Person" under two different emails → two nodes with
            # different ids (constraint-safe), one owning a.py, the other a.py
            # (overlap) + b.py.
            await g.ensure_contributor_node(email_a, "Dup Person")
            await g.ensure_contributor_node(email_b, "Dup Person")
            await g.add_ownership(email_a, repo_id, "a.py")
            await g.add_ownership(email_b, repo_id, "a.py")
            await g.add_ownership(email_b, repo_id, "b.py")

            contributors = await g.list_contributors()
            dup_rows = [c for c in contributors if c["name"] == "Dup Person"]

            assert len(dup_rows) == 1, f"expected one merged person, got {dup_rows}"
            row = dup_rows[0]
            assert row["files_owned"] == 2  # a.py + b.py, each counted once
            assert row["email"] in {email_a, email_b}
            assert row["repos"] == ["dedup-repo"]
            assert set(row["languages"]) == {"python"}
        finally:
            await g.run("MATCH (n) WHERE n.repo_id = $rid DETACH DELETE n", rid=repo_id)
            await g.run("MATCH (c:Contributor) WHERE c.email IN $es DETACH DELETE c",
                        es=[email_a, email_b])

    async def test_ensure_schema_dedupes_nodes_and_adds_constraint(self):
        """ensure_schema heals the concurrent-MERGE bug: it physically merges
        Contributor nodes that share an id (re-pointing their OWNS edges onto a
        single survivor) and then adds the uniqueness constraint that stops the
        duplicates from ever coming back."""
        from app.services.knowledge.graph import KnowledgeGraph
        from app.services.knowledge.graph_ids import node_id

        g = KnowledgeGraph()
        repo_id = "schema-test-repo"
        email = "schema-dup@example.com"
        same_id = node_id("", "Contributor", email)
        try:
            # Start from a clean slate: drop the constraint so we can recreate the
            # buggy same-id duplicates.
            await g.run("DROP CONSTRAINT contributor_id_unique IF EXISTS")
            await g.ensure_repo_node(repo_id, "schema-repo")
            await g.ensure_file_node(repo_id, "x.py", "python", 10)
            await g.ensure_file_node(repo_id, "y.py", "python", 20)
            x_fid = node_id(repo_id, "File", "x.py")
            y_fid = node_id(repo_id, "File", "y.py")

            # Two nodes with the SAME id (the bug), each owning a different file.
            await g.run("CREATE (c:Contributor {id: $id, email: $e, name: 'Schema Dup'})",
                        id=same_id, e=email)
            await g.run("CREATE (c:Contributor {id: $id, email: $e, name: 'Schema Dup'})",
                        id=same_id, e=email)
            # Each node owns one file, with an ownership weight that must survive
            # the merge (find_owner ranks reviewers by it).
            await g.run("MATCH (c:Contributor {id: $id}) WITH c LIMIT 1 "
                        "MATCH (f:File {id: $f}) MERGE (c)-[o:OWNS]->(f) SET o.weight = 5",
                        id=same_id, f=x_fid)
            await g.run("MATCH (c:Contributor {id: $id}) WITH c SKIP 1 LIMIT 1 "
                        "MATCH (f:File {id: $f}) MERGE (c)-[o:OWNS]->(f) SET o.weight = 5",
                        id=same_id, f=y_fid)

            before = (await g.run(
                "MATCH (c:Contributor {id: $id}) RETURN count(c) AS n", id=same_id))[0]["n"]
            assert before == 2

            await g.ensure_schema()

            after = await g.run(
                "MATCH (c:Contributor {id: $id}) RETURN count(c) AS n", id=same_id)
            assert after[0]["n"] == 1, "duplicate id nodes should be merged into one"

            # The survivor keeps BOTH owned files (edges re-pointed, not lost)…
            owned = await g.run(
                "MATCH (c:Contributor {id: $id})-[:OWNS]->(f:File) "
                "RETURN count(DISTINCT f) AS n", id=same_id)
            assert owned[0]["n"] == 2
            # …and the moved edge's ownership weight is carried over, not reset.
            weights = await g.run(
                "MATCH (c:Contributor {id: $id})-[o:OWNS]->(:File) RETURN o.weight AS w",
                id=same_id)
            assert all(row["w"] == 5 for row in weights), weights

            constraints = await g.run("SHOW CONSTRAINTS YIELD name RETURN collect(name) AS names")
            assert "contributor_id_unique" in constraints[0]["names"]
        finally:
            await g.run("MATCH (n) WHERE n.repo_id = $rid DETACH DELETE n", rid=repo_id)
            await g.run("MATCH (c:Contributor {email: $e}) DETACH DELETE c", e=email)
            # This test drops the constraint to recreate the buggy duplicates on
            # the SHARED graph; if it errored before ensure_schema re-added it,
            # restore the guard here so production is never left unprotected.
            await g.ensure_schema()


class TestTasksEndpoints:
    """The Tasks board is backed by the real `tasks` table — list, create, move
    (status change) and delete — not hardcoded frontend mock data."""

    async def test_list_tasks_empty_by_default(self, api_client):
        r = await api_client.get("/api/tasks")
        assert r.status_code == 200
        assert r.json() == []

    async def test_create_task_defaults_to_todo(self, api_client):
        r = await api_client.post("/api/tasks", json={"title": "Write the docs"})
        assert r.status_code == 201
        body = r.json()
        assert body["title"] == "Write the docs"
        assert body["status"] == "todo"
        assert body["id"]

    async def test_create_task_persists_fields(self, api_client):
        r = await api_client.post("/api/tasks", json={
            "title": "Add rate limiting", "priority": "high",
            "assignee": "yuji", "status": "doing",
        })
        assert r.status_code == 201
        body = r.json()
        assert body["priority"] == "high"
        assert body["assignee"] == "yuji"
        assert body["status"] == "doing"

        listed = (await api_client.get("/api/tasks")).json()
        assert any(t["id"] == body["id"] and t["title"] == "Add rate limiting" for t in listed)

    async def test_move_task_changes_status(self, api_client):
        created = (await api_client.post("/api/tasks", json={"title": "Move me"})).json()
        assert created["status"] == "todo"

        r = await api_client.patch(f"/api/tasks/{created['id']}", json={"status": "done"})
        assert r.status_code == 200
        assert r.json()["status"] == "done"

        listed = (await api_client.get("/api/tasks")).json()
        moved = next(t for t in listed if t["id"] == created["id"])
        assert moved["status"] == "done"

    async def test_update_unknown_task_returns_404(self, api_client):
        r = await api_client.patch("/api/tasks/00000000-0000-0000-0000-000000000000",
                                   json={"status": "done"})
        assert r.status_code == 404

    async def test_delete_task(self, api_client):
        created = (await api_client.post("/api/tasks", json={"title": "Delete me"})).json()
        r = await api_client.delete(f"/api/tasks/{created['id']}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

        listed = (await api_client.get("/api/tasks")).json()
        assert all(t["id"] != created["id"] for t in listed)

    async def test_create_task_rejects_invalid_status(self, api_client):
        """POST must reject an unknown status (422), mirroring PATCH — not
        silently coerce it to 'todo'."""
        r = await api_client.post("/api/tasks", json={"title": "x", "status": "nonsense"})
        assert r.status_code == 422

    async def test_create_task_rejects_overlong_title(self, api_client):
        """title maps to a varchar(500) column; reject at the edge (422) instead
        of letting it 500 at the database."""
        r = await api_client.post("/api/tasks", json={"title": "x" * 501})
        assert r.status_code == 422

    async def test_list_tasks_respects_limit(self, api_client):
        for i in range(3):
            await api_client.post("/api/tasks", json={"title": f"t{i}"})
        r = await api_client.get("/api/tasks", params={"limit": 2})
        assert r.status_code == 200
        assert len(r.json()) == 2


class TestLogsEndpoint:
    """The Logs page fetches /api/logs/{service} as plain text and splits it on
    newlines, one row per log line, so the level filters (INFO/WARN/…) work. The
    endpoint must return text/plain — a JSON-encoded string would escape every
    newline into a literal \\n and collapse the whole log into a single row."""

    async def test_logs_returned_as_plain_text(self, api_client):
        r = await api_client.get("/api/logs/api")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        # A JSON-serialized string body would start with a double-quote; plain
        # text must not.
        assert not r.text.startswith('"')

    async def test_unknown_service_is_plain_text(self, api_client):
        r = await api_client.get("/api/logs/does-not-exist")
        assert r.headers["content-type"].startswith("text/plain")
        assert "Unknown service" in r.text
        assert not r.text.startswith('"')


class TestApiAuthGate:
    """Data/mutation routers require an authenticated user; public routers
    (auth, webhooks) and /health stay open. Auth rides as a Bearer header or the
    HttpOnly tmx_token cookie."""

    async def test_gated_endpoint_rejects_anonymous(self, anon_client):
        r = await anon_client.get("/api/tasks")
        assert r.status_code == 401

    async def test_gated_mutation_rejects_anonymous(self, anon_client):
        r = await anon_client.post("/api/tasks", json={"title": "no auth"})
        assert r.status_code == 401

    async def test_gated_endpoint_allows_bearer(self, api_client):
        r = await api_client.get("/api/tasks")
        assert r.status_code == 200

    async def test_cookie_authenticates(self, anon_client):
        from app.utils.auth import create_token
        token = create_token("u", "u@example.com")
        r = await anon_client.get("/api/tasks", cookies={"tmx_token": token})
        assert r.status_code == 200

    async def test_invalid_token_rejected(self, anon_client):
        r = await anon_client.get("/api/tasks", cookies={"tmx_token": "garbage.token.value"})
        assert r.status_code == 401

    async def test_health_is_public(self, anon_client):
        r = await anon_client.get("/api/health")
        assert r.status_code == 200

    async def test_login_is_public_and_sets_httponly_cookie(self, anon_client, api_db):
        from app.models.user import User
        from app.utils.auth import hash_password

        api_db.add(User(email="gate@example.com", name="Gate",
                        hashed_password=hash_password("password123")))
        await api_db.flush()

        r = await anon_client.post("/api/auth/login",
                                   json={"email": "gate@example.com", "password": "password123"})
        assert r.status_code == 200
        set_cookie = r.headers.get("set-cookie", "")
        assert "tmx_token=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "samesite=lax" in set_cookie.lower()

    async def test_logout_is_public_and_clears_cookie(self, anon_client):
        r = await anon_client.post("/api/auth/logout")
        assert r.status_code == 200
        # Deleting a cookie = re-set it empty/expired.
        set_cookie = r.headers.get("set-cookie", "")
        assert "tmx_token=" in set_cookie
        assert ('Max-Age=0' in set_cookie) or ('expires=' in set_cookie.lower())


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


class TestPersona:
    """The agent's persona is read from app_config (key 'persona'), falling back
    to settings; unknown values normalize to the default. Each persona yields a
    distinct style directive."""

    async def test_resolve_persona_prefers_app_config(self, api_db):
        from app.models.app_config import AppConfig
        from app.services.agent.runtime import AgentRuntime

        api_db.add(AppConfig(key="persona", value={"persona": "reviewer"}))
        await api_db.flush()
        assert await AgentRuntime()._resolve_persona(api_db) == "reviewer"

    async def test_resolve_persona_unknown_falls_back_to_default(self, api_db):
        from app.models.app_config import AppConfig
        from app.services.agent.runtime import AgentRuntime
        from app.services.agent.prompts import DEFAULT_PERSONA

        api_db.add(AppConfig(key="persona", value={"persona": "bogus"}))
        await api_db.flush()
        assert await AgentRuntime()._resolve_persona(api_db) == DEFAULT_PERSONA

    async def test_resolve_persona_no_config_uses_default(self, api_db):
        from app.services.agent.runtime import AgentRuntime
        from app.services.agent.prompts import DEFAULT_PERSONA

        assert await AgentRuntime()._resolve_persona(api_db) == DEFAULT_PERSONA

    async def test_persona_directives_are_distinct(self):
        from app.services.agent.prompts import persona_directive, DEFAULT_PERSONA

        assert persona_directive("reviewer") != persona_directive("pragmatic")
        assert persona_directive("nonsense") == persona_directive(DEFAULT_PERSONA)


class TestPermissionEnforcement:
    """The runtime gates tools by capability: a disabled Permission row blocks
    the mapped tools before they dispatch; an absent row means allowed (the
    model defaults enabled)."""

    async def test_disabled_capability_blocks_tool(self, api_db):
        from app.models.permission import Permission
        from app.services.agent.runtime import AgentRuntime, AgentContext

        api_db.add(Permission(capability="write_code", enabled=False))
        await api_db.flush()

        ctx = AgentContext(repo_id=None, db=api_db)
        result = await AgentRuntime().execute_tool(
            ctx, "write_file", {"file_path": "/etc/zzz.py", "content": "x"},
        )
        assert "denied" in result.get("error", "").lower()

    async def test_absent_permission_allows_tool(self, api_db):
        from app.services.agent.runtime import AgentRuntime, AgentContext

        ctx = AgentContext(repo_id=None, db=api_db)
        # read_code has no row → allowed → dispatch runs (errors on the missing
        # file, but never with a permission denial).
        result = await AgentRuntime().execute_tool(
            ctx, "read_file", {"file_path": "/nonexistent/zzz.py"},
        )
        assert "denied" not in str(result).lower()


class TestPermissionsAPI:
    async def test_list_permissions_returns_defaults(self, api_client):
        r = await api_client.get("/api/permissions")
        assert r.status_code == 200
        perms = {p["capability"]: p["enabled"] for p in r.json()["permissions"]}
        assert perms["read_code"] is True
        assert perms["merge_pr"] is False  # off by default

    async def test_set_permission_persists(self, api_client):
        r = await api_client.put("/api/permissions/write_code", json={"enabled": False})
        assert r.status_code == 200
        perms = {p["capability"]: p["enabled"]
                 for p in (await api_client.get("/api/permissions")).json()["permissions"]}
        assert perms["write_code"] is False

    async def test_set_unknown_capability_404(self, api_client):
        r = await api_client.put("/api/permissions/bogus", json={"enabled": True})
        assert r.status_code == 404


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
