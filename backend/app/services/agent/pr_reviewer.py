import json
from structlog import get_logger

from app.services.knowledge.graph import KnowledgeGraph
from app.services.agent.rag import classify_query_intent

logger = get_logger(__name__)


class PRReviewer:
    def __init__(self):
        self.graph = KnowledgeGraph()

    async def review(self, repo_id: str, repo_name: str, pr_title: str,
                     pr_body: str = "", changed_files: list[str] | None = None,
                     diff: str = "") -> dict:
        changed_files = changed_files or []
        issues: list[dict] = []
        suggestions: list[dict] = []

        for file_path in changed_files:
            file_issues = await self._review_file(repo_id, file_path)
            issues.extend(file_issues)

        if diff:
            diff_issues = self._scan_diff(diff, repo_name)
            issues.extend(diff_issues)

        if pr_title or pr_body:
            info_issues = await self._review_pr_info(repo_id, pr_title, pr_body, changed_files)
            issues.extend(info_issues)

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        issues.sort(key=lambda i: severity_order.get(i.get("severity", "low"), 4))

        return {
            "repo": repo_name,
            "files_reviewed": len(changed_files),
            "issues_found": len(issues),
            "issues": issues,
            "summary": self._build_summary(issues, changed_files),
        }

    async def _review_file(self, repo_id: str, file_path: str) -> list[dict]:
        issues = []

        owner = await self.graph.find_owner(repo_id, file_path)
        deps = await self.graph.find_dependencies(repo_id, file_path)

        if deps and len(deps) > 10:
            issues.append({
                "file": file_path,
                "severity": "medium",
                "type": "high_coupling",
                "message": f"High coupling: {len(deps)} dependencies. Consider splitting responsibilities.",
            })

        if owner is None:
            issues.append({
                "file": file_path,
                "severity": "low",
                "type": "no_owner",
                "message": "No owner identified. Consider adding CODEOWNERS.",
            })

        return issues

    def _scan_diff(self, diff: str, repo_name: str) -> list[dict]:
        issues = []

        if "secret" in diff.lower() or "password" in diff.lower() or "api_key" in diff.lower():
            issues.append({
                "file": "multiple",
                "severity": "critical",
                "type": "secret_exposure",
                "message": "Potential secret/password in diff. Verify these are not committing real credentials.",
            })

        if "print(" in diff and "print(\"" not in diff:
            issues.append({
                "file": "multiple",
                "severity": "low",
                "type": "debug_code",
                "message": "Debug print statements found — consider removing before merge.",
            })

        if "TODO" in diff or "FIXME" in diff or "HACK" in diff:
            issues.append({
                "file": "multiple",
                "severity": "medium",
                "type": "unresolved_todos",
                "message": "TODO/FIXME/HACK comments in diff — resolve or file a ticket.",
            })

        return issues

    async def _review_pr_info(self, repo_id: str, title: str, body: str,
                              changed_files: list[str]) -> list[dict]:
        issues = []
        nfiles = len(changed_files)

        if nfiles == 0:
            issues.append({
                "file": "",
                "severity": "low",
                "type": "no_files",
                "message": "PR has no changed files — may need verification.",
            })
        elif nfiles > 20:
            issues.append({
                "file": "",
                "severity": "medium",
                "type": "large_pr",
                "message": f"Large PR ({nfiles} files) — consider breaking into smaller, focused PRs.",
            })

        return issues

    def _build_summary(self, issues: list[dict], changed_files: list[str]) -> str:
        if not issues:
            return f"✓ No issues found across {len(changed_files)} files. Looks good!"

        critical = [i for i in issues if i["severity"] == "critical"]
        high = [i for i in issues if i["severity"] == "high"]
        medium = [i for i in issues if i["severity"] == "medium"]

        lines = []
        if critical:
            lines.append(f"🚨 **{len(critical)} critical** issues")
        if high:
            lines.append(f"⚠️ **{len(high)} high** severity")
        if medium:
            lines.append(f"📋 **{len(medium)} medium** severity")
        lines.append(f"across {len(changed_files)} files")
        return " — ".join(lines)


pr_reviewer = PRReviewer()
