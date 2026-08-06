from dataclasses import dataclass, field
from pathlib import Path

from pydriller import Repository as DrillerRepo
from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class ContributorProfile:
    name: str
    email: str
    commit_count: int
    files_touched: int
    lines_added: int
    lines_deleted: int
    first_commit: str | None
    last_commit: str | None
    owned_files: list[str] = field(default_factory=list)
    owned_modules: list[str] = field(default_factory=list)
    review_count: int = 0


class PeopleProfiler:
    MAX_COMMITS = 10000

    def profile_repo(self, clone_path: str) -> dict[str, ContributorProfile]:
        profiles: dict[str, ContributorProfile] = {}
        file_contributors: dict[str, set[str]] = {}

        try:
            commit_count = 0
            for commit in DrillerRepo(clone_path).traverse_commits():
                email = commit.author.email.lower()
                if email not in profiles:
                    profiles[email] = ContributorProfile(
                        name=commit.author.name,
                        email=email,
                        commit_count=0,
                        files_touched=0,
                        lines_added=0,
                        lines_deleted=0,
                        first_commit=str(commit.author_date),
                        last_commit=str(commit.author_date),
                    )

                profile = profiles[email]
                profile.commit_count += 1
                profile.lines_added += (
                    getattr(commit, "lines", 0) or getattr(commit, "lines_added", 0) or 0
                )
                profile.lines_deleted += (
                    getattr(commit, "deletions", 0) or getattr(commit, "lines_deleted", 0) or 0
                )
                profile.last_commit = str(commit.author_date)

                for modified in commit.modified_files:
                    fpath = modified.new_path or modified.old_path
                    if fpath:
                        profile.files_touched += 1
                        if fpath not in file_contributors:
                            file_contributors[fpath] = set()
                        file_contributors[fpath].add(email)

                commit_count += 1
                if commit_count >= self.MAX_COMMITS:
                    break

        except Exception as e:
            logger.error("profile_failed", path=clone_path, error=str(e))
            return profiles

        # Determine file ownership (contributor with most commits to a file)
        ownership = self._compute_ownership(file_contributors, profiles)
        for email, files in ownership.items():
            if email in profiles:
                profiles[email].owned_files = files

        for profile in profiles.values():
            modules: set[str] = set()
            for f in profile.owned_files:
                parts = Path(f).parts
                if len(parts) > 1:
                    modules.add(parts[0])
            profile.owned_modules = sorted(modules)

        return profiles

    def _compute_ownership(
        self,
        file_contributors: dict[str, set[str]],
        profiles: dict[str, ContributorProfile],
    ) -> dict[str, list[str]]:
        file_owner: dict[str, str] = {}
        for fpath, contributors in file_contributors.items():
            if contributors:
                file_owner[fpath] = max(
                    contributors,
                    key=lambda e: profiles[e].commit_count if e in profiles else 0,
                )

        ownership: dict[str, list[str]] = {}
        for fpath, owner in file_owner.items():
            if owner not in ownership:
                ownership[owner] = []
            ownership[owner].append(fpath)

        return ownership
