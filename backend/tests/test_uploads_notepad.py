"""API tests for the per-user uploads and notepad features."""

import pytest

# Bind to the session event loop, matching the session-scoped api_client/api_db
# fixtures (same pattern as test_api.py).
pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestUploads:
    async def test_upload_list_download_delete_roundtrip(self, api_client, monkeypatch, tmp_path):
        monkeypatch.setattr("app.api.uploads.UPLOAD_ROOT", tmp_path)

        # Upload
        r = await api_client.post(
            "/api/uploads",
            files={"file": ("hello.txt", b"hello world", "text/plain")},
        )
        assert r.status_code == 201, r.text
        meta = r.json()
        assert meta["filename"] == "hello.txt"
        assert meta["size_bytes"] == 11
        uid = meta["id"]

        # List shows it
        listed = (await api_client.get("/api/uploads")).json()
        assert any(u["id"] == uid for u in listed)

        # Download returns the bytes as an attachment (never inline)
        dl = await api_client.get(f"/api/uploads/{uid}/download")
        assert dl.status_code == 200
        assert dl.content == b"hello world"
        assert "attachment" in dl.headers.get("content-disposition", "")

        # Delete, then it's gone
        d = await api_client.delete(f"/api/uploads/{uid}")
        assert d.status_code == 204
        assert (await api_client.get("/api/uploads")).json() == []

    async def test_upload_rejects_oversized(self, api_client, monkeypatch, tmp_path):
        monkeypatch.setattr("app.api.uploads.UPLOAD_ROOT", tmp_path)
        monkeypatch.setattr("app.api.uploads.MAX_UPLOAD_BYTES", 8)
        r = await api_client.post(
            "/api/uploads",
            files={"file": ("big.bin", b"way too many bytes", "application/octet-stream")},
        )
        assert r.status_code == 413

    async def test_upload_rejects_empty(self, api_client, monkeypatch, tmp_path):
        monkeypatch.setattr("app.api.uploads.UPLOAD_ROOT", tmp_path)
        r = await api_client.post("/api/uploads", files={"file": ("empty.txt", b"", "text/plain")})
        assert r.status_code == 400

    async def test_download_unknown_id_404(self, api_client):
        import uuid

        r = await api_client.get(f"/api/uploads/{uuid.uuid4()}/download")
        assert r.status_code == 404

    async def test_download_malformed_id_404_not_500(self, api_client):
        r = await api_client.get("/api/uploads/not-a-uuid/download")
        assert r.status_code == 404

    async def test_requires_auth(self, anon_client):
        assert (await anon_client.get("/api/uploads")).status_code == 401


class TestNotepad:
    async def test_get_default_is_empty(self, api_client):
        r = await api_client.get("/api/notepad")
        assert r.status_code == 200
        assert r.json()["content"] == ""

    async def test_save_then_roundtrip(self, api_client):
        saved = await api_client.post(
            "/api/notepad", json={"content": "# my scratch\nremember this"}
        )
        assert saved.status_code == 200
        assert saved.json()["content"] == "# my scratch\nremember this"

        got = (await api_client.get("/api/notepad")).json()
        assert got["content"] == "# my scratch\nremember this"
        assert got["updated_at"] is not None

    async def test_save_overwrites(self, api_client):
        await api_client.post("/api/notepad", json={"content": "first"})
        await api_client.post("/api/notepad", json={"content": "second"})
        assert (await api_client.get("/api/notepad")).json()["content"] == "second"

    async def test_requires_auth(self, anon_client):
        assert (await anon_client.get("/api/notepad")).status_code == 401
