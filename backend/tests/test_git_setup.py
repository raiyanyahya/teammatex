"""Tests for resolving a GitHub token from the available sources (env, DB
app_config, or an existing clone's remote URL), used to auto-configure git+gh
at startup so the teammate can push/PR after any rebuild."""

from app.services.agent.git_setup import resolve_github_token


def test_prefers_env_token():
    assert resolve_github_token(env_token="env_tok") == "env_tok"


def test_env_takes_precedence_over_db():
    assert resolve_github_token(env_token="e", db_value={"token": "d"}) == "e"


def test_db_dict_value():
    assert resolve_github_token(db_value={"token": "db_tok"}) == "db_tok"


def test_db_json_string_value():
    assert resolve_github_token(db_value='{"token": "db_tok"}') == "db_tok"


def test_extracts_from_remote_url():
    url = "https://x-access-token:ghp_xyz@github.com/o/r.git"
    assert resolve_github_token(remote_url=url) == "ghp_xyz"


def test_none_when_no_sources():
    assert resolve_github_token() is None
