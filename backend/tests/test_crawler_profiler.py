"""Test the git crawler — language detection, file counting."""

from app.services.onboarding.git_crawler import GitCrawler


class TestGitCrawler:
    def test_language_detection(self, tmp_repo_dir):
        crawler = GitCrawler()
        languages = crawler._detect_languages(str(tmp_repo_dir))

        assert "Python" in languages
        assert languages["Python"] >= 2

        assert "JavaScript" in languages
        assert languages["JavaScript"] >= 1

    def test_file_counting(self, tmp_repo_dir):
        crawler = GitCrawler()
        count = crawler._count_files(str(tmp_repo_dir))

        assert count >= 3

    def test_existing_clone_detection(self, tmp_repo_dir):
        crawler = GitCrawler()
        assert crawler.check_existing_clone(str(tmp_repo_dir)) is True

    def test_nonexistent_clone(self, tmp_path):
        crawler = GitCrawler()
        assert crawler.check_existing_clone(str(tmp_path / "nope")) is False

    def test_language_map_coverage(self):
        crawler = GitCrawler()
        # Create a temp file with .py extension
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            py_file = os.path.join(tmpdir, "test.py")
            with open(py_file, "w") as f:
                f.write("print('hello')")
            js_file = os.path.join(tmpdir, "test.js")
            with open(js_file, "w") as f:
                f.write("console.log('hello')")
            go_file = os.path.join(tmpdir, "test.go")
            with open(go_file, "w") as f:
                f.write("package main")

            langs = crawler._detect_languages(tmpdir)
            assert "Python" in langs
            assert "JavaScript" in langs
            assert "Go" in langs


class TestPeopleProfiler:
    def test_empty_repo(self, tmp_path):
        from app.services.onboarding.people_profiler import PeopleProfiler

        (tmp_path / ".git").mkdir()
        profiler = PeopleProfiler()
        profiles = profiler.profile_repo(str(tmp_path))
        assert isinstance(profiles, dict)
        assert len(profiles) == 0

    def test_ownership_computation(self):
        from app.services.onboarding.people_profiler import ContributorProfile, PeopleProfiler

        profiler = PeopleProfiler()
        file_contributors = {
            "src/auth.py": {"alice@test.com", "bob@test.com"},
            "src/payment.py": {"alice@test.com"},
            "tests/test_auth.py": {"bob@test.com"},
        }
        profiles = {
            "alice@test.com": ContributorProfile(
                name="Alice",
                email="alice@test.com",
                commit_count=10,
                files_touched=3,
                lines_added=100,
                lines_deleted=20,
                first_commit="2024-01-01",
                last_commit="2024-06-01",
            ),
            "bob@test.com": ContributorProfile(
                name="Bob",
                email="bob@test.com",
                commit_count=5,
                files_touched=2,
                lines_added=50,
                lines_deleted=10,
                first_commit="2024-02-01",
                last_commit="2024-05-01",
            ),
        }

        ownership = profiler._compute_ownership(file_contributors, profiles)

        assert "alice@test.com" in ownership
        assert "bob@test.com" in ownership

        alice_files = ownership["alice@test.com"]
        assert "src/auth.py" in alice_files
        assert "src/payment.py" in alice_files

        bob_files = ownership["bob@test.com"]
        assert "tests/test_auth.py" in bob_files
