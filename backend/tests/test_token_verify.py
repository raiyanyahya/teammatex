"""Tests for GitHub token classification (read-only vs write detection)."""

from app.services.agent.git_setup import classify_github_token


def test_classic_token_with_repo_scope_can_push():
    r = classify_github_token("ghp_abc123", "repo, read:org")
    assert r["token_type"] == "classic"
    assert r["can_push"] is True
    assert "repo" in r["scopes"]


def test_classic_token_public_repo_only():
    r = classify_github_token("ghp_abc123", "public_repo")
    assert r["can_push"] is True
    assert "public" in r["note"].lower()


def test_classic_token_without_repo_scope_is_read_only():
    r = classify_github_token("ghp_abc123", "read:user, gist")
    assert r["can_push"] is False
    assert "read-only" in r["note"].lower()


def test_fine_grained_token_push_unknown():
    r = classify_github_token("github_pat_xyz", None)
    assert r["token_type"] == "fine-grained"
    assert r["can_push"] is None
    assert "fine-grained" in r["note"].lower()


def test_unknown_token_type():
    r = classify_github_token("randomstring", None)
    assert r["token_type"] == "unknown"
    assert r["can_push"] is None
