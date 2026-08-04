from dataclasses import dataclass, field
from pathlib import Path

from pygit2.errors import GitError
from structlog import get_logger

from app.config import settings
from app.utils.git import clone_or_pull

logger = get_logger(__name__)


@dataclass
class RepoInfo:
    name: str = ""
    url: str = ""
    default_branch: str = ""
    branches: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    commit_count: int = 0
    contributor_count: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    total_files: int = 0
    clone_path: str = ""


class GitCrawler:
    CLONE_ROOT = "/data/repos"

    def crawl(self, github_url: str, local_name: str) -> RepoInfo:
        # Defense in depth: the API sanitizes local_name, but confirm the target
        # still resolves inside CLONE_ROOT so a traversal name can never write a
        # clone outside the repos volume.
        root = Path(self.CLONE_ROOT).resolve()
        clone_path = str(Path(self.CLONE_ROOT) / local_name)
        resolved = Path(clone_path).resolve()
        if resolved != root and root not in resolved.parents:
            raise GitError(f"Refusing to clone outside {self.CLONE_ROOT}: {local_name!r}")
        token = self._get_github_token()
        try:
            repo = clone_or_pull(github_url, clone_path, token=token)
        except GitError as e:
            msg = str(e)
            if "404" in msg or "not found" in msg.lower():
                raise GitError(
                    f"Repository not found: {github_url}. "
                    "Make sure the URL is a full repo path like github.com/owner/repo-name. "
                    "For private repos, save your GitHub token in Settings first."
                ) from e
            raise
        info = self._extract_info(repo, github_url, local_name, clone_path)
        return info

    def _get_github_token(self) -> str:
        try:
            from sqlalchemy import create_engine, select

            from app.models.app_config import AppConfig

            engine = create_engine(
                settings.database_url.replace("+asyncpg", "+psycopg2"),
                pool_pre_ping=True,
            )
            with engine.connect() as conn:
                result = conn.execute(select(AppConfig).where(AppConfig.key == "github_token"))
                row = result.mappings().first()
                if row and row.get("value"):
                    return row["value"].get("token", "")
        except Exception:
            pass
        return ""

    def _extract_info(self, repo, github_url: str, local_name: str, clone_path: str) -> RepoInfo:
        info = RepoInfo()
        info.name = local_name
        info.url = github_url
        info.clone_path = clone_path

        default = repo.head.shorthand if not repo.head_is_unborn else "main"
        info.default_branch = default

        branches = [
            ref.replace("refs/heads/", "")
            for ref in repo.listall_references()
            if ref.startswith("refs/heads/")
        ]
        info.branches = branches

        tags = [
            ref.replace("refs/tags/", "")
            for ref in repo.listall_references()
            if ref.startswith("refs/tags/")
        ]
        info.tags = tags

        # Count commits and contributors via pydriller
        commit_count = 0
        contributors: set[str] = set()
        try:
            from pydriller import Repository as DrillerRepo

            for commit in DrillerRepo(clone_path).traverse_commits():
                commit_count += 1
                contributors.add(commit.author.email)
                if commit_count >= 10000:
                    logger.warning("commit_limit_reached", repo=local_name, limit=10000)
                    break
        except Exception as e:
            logger.error("commit_scan_failed", repo=local_name, error=str(e))

        info.commit_count = commit_count
        info.contributor_count = len(contributors)

        # Detect languages
        info.languages = self._detect_languages(clone_path)

        # Count files
        info.total_files = self._count_files(clone_path)

        return info

    def _detect_languages(self, clone_path: str) -> dict[str, int]:
        extensions = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".jsx": "JavaScript",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".rb": "Ruby",
            ".c": "C",
            ".cpp": "C++",
            ".h": "C/C++",
            ".css": "CSS",
            ".html": "HTML",
            ".json": "JSON",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".md": "Markdown",
            ".sql": "SQL",
            ".sh": "Shell",
            ".toml": "TOML",
        }
        counts: dict[str, int] = {}
        root = Path(clone_path)
        for f in root.rglob("*"):
            if f.is_file() and ".git" not in f.parts:
                ext = f.suffix.lower()
                if ext in extensions:
                    lang = extensions[ext]
                    counts[lang] = counts.get(lang, 0) + 1
        return counts

    def _count_files(self, clone_path: str) -> int:
        count = 0
        root = Path(clone_path)
        for f in root.rglob("*"):
            if f.is_file() and ".git" not in f.parts:
                count += 1
        return count

    def check_existing_clone(self, local_name: str) -> bool:
        path = Path(self.CLONE_ROOT) / local_name / ".git"
        return path.exists()
