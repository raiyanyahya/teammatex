"""Tests for the environment context builder. Disk is authoritative (so the
bogus 'blockstacks' org row, which has no clone, is dropped); the DB enriches
on-disk repos with language/branch metadata."""

from app.services.agent.environment import format_environment_block, reconcile_repos


class TestReconcileRepos:
    DB = [
        {"local_name": "kit-fork", "language": "JavaScript",
         "default_branch": "master", "github_url": "https://github.com/blockstacks/kit-fork.git"},
        {"local_name": "blockstacks", "language": None,
         "default_branch": None, "github_url": "github.com/blockstacks"},
    ]

    def test_disk_authoritative_drops_db_only_rows(self):
        out = reconcile_repos(self.DB, {"kit-fork", "zapq-frk"})
        assert [r["name"] for r in out] == ["kit-fork", "zapq-frk"]  # sorted, no blockstacks

    def test_db_metadata_enriches_matching_repo(self):
        out = reconcile_repos(self.DB, {"kit-fork"})
        kit = out[0]
        assert kit["path"] == "/data/repos/kit-fork"
        assert kit["language"] == "JavaScript"
        assert kit["default_branch"] == "master"

    def test_disk_only_repo_gets_defaults(self):
        out = reconcile_repos(self.DB, {"zapq-frk"})
        z = out[0]
        assert z["path"] == "/data/repos/zapq-frk"
        assert z["default_branch"] == "main"  # default when DB has no row

    def test_empty_disk_yields_nothing(self):
        assert reconcile_repos(self.DB, set()) == []


class TestFormatEnvironmentBlock:
    def test_lists_repo_name_path_lang_branch(self):
        repos = [{"name": "kit-fork", "path": "/data/repos/kit-fork",
                  "language": "JavaScript", "default_branch": "master",
                  "github_url": "https://github.com/blockstacks/kit-fork.git", "entries": []}]
        block = format_environment_block(repos)
        assert "kit-fork" in block
        assert "/data/repos/kit-fork" in block
        assert "JavaScript" in block
        assert "master" in block

    def test_includes_top_level_entries_when_present(self):
        repos = [{"name": "a", "path": "/data/repos/a", "language": "Python",
                  "default_branch": "main", "github_url": "", "entries": ["src", "README.md"]}]
        block = format_environment_block(repos)
        assert "src" in block and "README.md" in block

    def test_handles_no_repos(self):
        assert "no repositories" in format_environment_block([]).lower()
