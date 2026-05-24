from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.services.llm.provider import LLMProvider

logger = get_logger(__name__)


class IncidentResponseAssistant:
    async def analyze_incident(
        self, db: AsyncSession, repo_name: str, incident_description: str,
    ) -> dict:
        recent_commits = await self._get_recent_commits()
        recent_prs = await self._get_recent_prs(db)

        context = f"Recent commits: {len(recent_commits)}\nRecent PRs: {len(recent_prs)}"

        prompt = f"""Analyze this incident and identify likely causes.

Repository: {repo_name}
Incident description: {incident_description}

Context:
{context}

Provide:
1. Likely root cause analysis
2. Related recent changes
3. Recommended immediate action
4. Suggested rollback or hotfix
5. Post-incident follow-up items
"""
        analysis = await LLMProvider.simple_prompt(
            system="You are an incident response analyst. Be thorough and precise.",
            user=prompt,
            temperature=0.1,
        )

        return {
            "incident": incident_description,
            "analysis": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def generate_postmortem(
        self, incident_description: str, timeline: list[dict], resolution: str,
    ) -> str:
        timeline_text = "\n".join(
            f"- {e.get('time', 'N/A')}: {e.get('event', '')}"
            for e in timeline
        )
        prompt = f"""Generate a post-incident analysis.

Incident: {incident_description}
Timeline:
{timeline_text}
Resolution: {resolution}

Include:
1. Summary
2. Timeline of events
3. Root cause analysis
4. Impact assessment
5. Resolution steps
6. Preventive measures
7. Action items
"""
        return await LLMProvider.simple_prompt(
            system="You write clear, thorough post-incident reports in markdown.",
            user=prompt,
            temperature=0.1,
        )

    async def _get_recent_commits(self) -> list[dict]:
        return []

    async def _get_recent_prs(self, db: AsyncSession) -> list[dict]:
        from app.models.pr import PR
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        result = await db.execute(
            select(PR).where(PR.created_at >= cutoff).order_by(PR.created_at.desc()).limit(20)
        )
        return [{"title": p.title, "branch": p.branch, "status": p.status} for p in result.scalars().all()]


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

    def compute_velocity(self, completed: list[dict], sprint_days: int = 10) -> dict:
        points_total = sum(
            3 if i.get("priority") == "high" else 2 if i.get("priority") == "medium" else 1
            for i in completed
        )
        return {
            "total_completed": len(completed),
            "estimated_points": points_total,
            "sprint_days": sprint_days,
            "points_per_day": round(points_total / max(1, sprint_days), 1),
        }

    def detect_bottlenecks(self, issues: list[dict]) -> list[dict]:
        status_counts: dict[str, int] = {}
        for issue in issues:
            status = issue.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        bottlenecks: list[dict] = []
        stuck_states = {"in_review", "blocked", "waiting"}
        for status, count in status_counts.items():
            if status.lower() in stuck_states or count > len(issues) * 0.3:
                bottlenecks.append({
                    "status": status,
                    "count": count,
                    "percentage": round(count / max(1, len(issues)) * 100, 1),
                })

        return bottlenecks


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


class MeetingActionItemExtractor:
    async def extract(self, transcript: str) -> list[dict]:
        prompt = f"""Extract action items and decisions from this meeting transcript.

For each action item, identify:
- description: clear task description
- assignee: who should do it (or "unassigned")
- priority: high, medium, or low

Transcript:
{transcript[:8000]}

Return a JSON array of action items.
"""
        result = await LLMProvider.simple_prompt(
            system="You extract action items from meeting transcripts. Return JSON only.",
            user=prompt,
            temperature=0.1,
        )
        try:
            import json
            items = json.loads(result.split("```json")[1].split("```")[0].strip() if "```json" in result else result)
            return items if isinstance(items, list) else []
        except Exception:
            return [{"description": result[:500], "assignee": "unassigned", "priority": "medium"}]
