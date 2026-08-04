"""Server-side conversation history + chat attachment injection."""

import json
import uuid

import pytest

# ── Conversation endpoints (scoped to the caller's JWT sub) ──────────────────


# Endpoint tests share the session-scoped api_client/api_db loop; the attachment
# tests below use the function-scoped async_db, so loop scope is set per class.
@pytest.mark.asyncio(loop_scope="session")
class TestConversationEndpoints:
    async def test_list_starts_empty(self, api_client):
        r = await api_client.get("/api/conversations")
        assert r.status_code == 200
        assert r.json() == []

    async def test_chat_creates_conversation_and_persists_turn(self, api_client, monkeypatch):
        # Stub the agent so no LLM/RAG runs: emit one text event like the loop does.
        async def fake_chat(db, message, repo_id=None, history=None):
            yield 'data: {"type": "text", "content": "Hi, I am the answer."}\n\n'

        monkeypatch.setattr("app.api.agent.agent_runtime.chat", fake_chat)

        r = await api_client.post("/api/agent/chat", json={"message": "hello there"})
        assert r.status_code == 200
        body = r.text
        # The stream announces the conversation id up front.
        convo_id = None
        for line in body.splitlines():
            if line.startswith("data: ") and line[6:] != "[DONE]":
                data = json.loads(line[6:])
                if data.get("type") == "conversation":
                    convo_id = data["id"]
        assert convo_id, body

        # It now shows in the list, titled from the first message.
        listed = (await api_client.get("/api/conversations")).json()
        assert any(c["id"] == convo_id and c["title"] == "hello there" for c in listed)

        # And both turns were persisted (original user text, not augmented).
        convo = (await api_client.get(f"/api/conversations/{convo_id}")).json()
        roles = [(m["role"], m["content"]) for m in convo["messages"]]
        assert roles == [("user", "hello there"), ("assistant", "Hi, I am the answer.")]

    async def test_second_turn_appends_to_same_conversation(self, api_client, monkeypatch):
        async def fake_chat(db, message, repo_id=None, history=None):
            yield 'data: {"type": "text", "content": "answer two"}\n\n'

        monkeypatch.setattr("app.api.agent.agent_runtime.chat", fake_chat)

        first = await api_client.post("/api/agent/chat", json={"message": "q1"})
        cid = next(
            json.loads(l[6:])["id"]
            for l in first.text.splitlines()
            if l.startswith("data: ")
            and l[6:] != "[DONE]"
            and json.loads(l[6:]).get("type") == "conversation"
        )
        await api_client.post("/api/agent/chat", json={"message": "q2", "conversation_id": cid})

        convo = (await api_client.get(f"/api/conversations/{cid}")).json()
        assert [m["content"] for m in convo["messages"]] == [
            "q1",
            "answer two",
            "q2",
            "answer two",
        ]

    async def test_delete_conversation(self, api_client, monkeypatch):
        async def fake_chat(db, message, repo_id=None, history=None):
            yield 'data: {"type": "text", "content": "x"}\n\n'

        monkeypatch.setattr("app.api.agent.agent_runtime.chat", fake_chat)
        r = await api_client.post("/api/agent/chat", json={"message": "delete me"})
        cid = next(
            json.loads(l[6:])["id"]
            for l in r.text.splitlines()
            if l.startswith("data: ")
            and l[6:] != "[DONE]"
            and json.loads(l[6:]).get("type") == "conversation"
        )
        d = await api_client.delete(f"/api/conversations/{cid}")
        assert d.status_code == 204
        assert (await api_client.get(f"/api/conversations/{cid}")).status_code == 404

    async def test_get_unknown_id_404(self, api_client):
        assert (await api_client.get(f"/api/conversations/{uuid.uuid4()}")).status_code == 404

    async def test_get_malformed_id_404_not_500(self, api_client):
        assert (await api_client.get("/api/conversations/not-a-uuid")).status_code == 404

    async def test_requires_auth(self, anon_client):
        assert (await anon_client.get("/api/conversations")).status_code == 401


# ── Attachment injection (inline file text) ──────────────────────────────────


class TestAttachmentInjection:
    async def _make_upload(self, db, owner, filename, data: bytes, tmp_path):
        from app.models.upload import Upload

        p = tmp_path / uuid.uuid4().hex
        p.write_bytes(data)
        up = Upload(
            owner_id=owner,
            filename=filename,
            content_type="text/plain",
            size_bytes=len(data),
            stored_path=str(p),
        )
        db.add(up)
        await db.flush()
        return up

    async def test_prepends_text_file(self, async_db, tmp_path):
        from app.services.agent.attachments import build_attached_message

        up = await self._make_upload(
            async_db, "owner-1", "notes.txt", b"line one\nline two", tmp_path
        )
        out = await build_attached_message(async_db, up.id, "owner-1", "summarize this")
        assert "notes.txt" in out
        assert "line one" in out
        assert out.rstrip().endswith("summarize this")

    async def test_truncates_large_file(self, async_db, tmp_path, monkeypatch):
        import app.services.agent.attachments as att

        monkeypatch.setattr(att, "ATTACH_MAX_BYTES", 10)
        up = await self._make_upload(async_db, "owner-1", "big.txt", b"x" * 5000, tmp_path)
        out = await att.build_attached_message(async_db, up.id, "owner-1", "go")
        assert "truncated" in out.lower()
        assert out.count("x") <= 20  # only the capped slice, not all 5000

    async def test_binary_file_noted_not_garbled(self, async_db, tmp_path):
        from app.services.agent.attachments import build_attached_message

        up = await self._make_upload(
            async_db, "owner-1", "img.png", b"\x89PNG\x00\xff\xfe", tmp_path
        )
        out = await build_attached_message(async_db, up.id, "owner-1", "what is this")
        assert "binary" in out.lower()
        assert out.rstrip().endswith("what is this")

    async def test_foreign_upload_ignored(self, async_db, tmp_path):
        from app.services.agent.attachments import build_attached_message

        up = await self._make_upload(async_db, "owner-1", "secret.txt", b"private", tmp_path)
        # A different owner must not get the file content injected.
        out = await build_attached_message(async_db, up.id, "owner-2", "hi")
        assert out == "hi"
        assert "private" not in out

    async def test_missing_and_malformed_ids_ignored(self, async_db):
        from app.services.agent.attachments import build_attached_message

        assert await build_attached_message(async_db, None, "o", "hi") == "hi"
        assert await build_attached_message(async_db, "not-a-uuid", "o", "hi") == "hi"
        assert await build_attached_message(async_db, str(uuid.uuid4()), "o", "hi") == "hi"
