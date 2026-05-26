from datetime import datetime

from structlog import get_logger

from app.services.llm.provider import LLMProvider

logger = get_logger(__name__)


class SprintRetrospectiveAssistant:
    async def generate_retrospective(
        self, sprint_name: str, completed: list[dict], planned: list[dict],
    ) -> str:
        completed_text = "\n".join(
            f"- [{i.get('status', '?')}] {i.get('title', '')}"
            for i in completed[:50]
        )
        planned_text = "\n".join(
            f"- {i.get('title', '')}"
            for i in planned[:10]
        )

        prompt = f"""Generate a sprint retrospective summary.

Sprint: {sprint_name}
Completed items ({len(completed)}):
{completed_text}

Planned but not completed:
{planned_text}

Analyze:
1. What went well this sprint
2. What could be improved
3. Bottlenecks identified
4. Velocity observations
5. Action items for next sprint
6. Celebrations and shoutouts
"""
        return await LLMProvider.simple_prompt(
            system="You are a thoughtful scrum master facilitating a sprint retrospective.",
            user=prompt,
        )


class GitHygieneAutomation:
    STALE_BRANCH_DAYS = 60
    MERGED_BRANCH_PATTERNS = ["teammatex/", "feature/", "fix/", "hotfix/"]

    async def analyze(self, repo_path: str) -> dict:
        import pygit2
        from datetime import timezone as tz

        repo = pygit2.Repository(repo_path)
        stale_branches: list[dict] = []
        merged_branches: list[str] = []
        now = datetime.now(tz.utc)

        for ref in repo.listall_references():
            if not ref.startswith("refs/heads/"):
                continue
            branch_name = ref.replace("refs/heads/", "")

            if branch_name in ("main", "master", "develop"):
                continue

            try:
                commit = repo.lookup_reference(ref).peel()
            except Exception:
                continue

            if hasattr(commit, "commit_time"):
                branch_date = datetime.fromtimestamp(commit.commit_time, tz=tz.utc)
                days_old = (now - branch_date).days
                if days_old > self.STALE_BRANCH_DAYS:
                    stale_branches.append({
                        "branch": branch_name,
                        "days_old": days_old,
                        "last_commit": branch_date.isoformat(),
                    })

            for pattern in self.MERGED_BRANCH_PATTERNS:
                if branch_name.startswith(pattern):
                    merged_branches.append(branch_name)
                    break

        return {
            "stale_branches": stale_branches,
            "merged_candidates": merged_branches[:50],
            "total_branches": len(list(repo.listall_references())),
        }


class SelfUpdatingKnowledge:
    async def handle_push_webhook(self, repo_id: str, branch: str, commits: int) -> dict:
        logger.info("push_detected", repo_id=repo_id, branch=branch, commits=commits)

        return {
            "repo_id": repo_id,
            "branch": branch,
            "commits": commits,
            "action": "Trigger incremental re-sync for changed files",
        }

    async def detect_stale_knowledge(self) -> list[dict]:
        return []
