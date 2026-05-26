import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional

import httpx
from structlog import get_logger

from app.config import settings
from app.services.integrations.base import (
    PRInfo,
    RepoInfo,
    SCMProvider,
    IntegrationRegistry,
)

logger = get_logger(__name__)


class GitHubProvider(SCMProvider):
    provider_name = "github"
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None):
        self.token = token or settings.github_client_secret
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )

    async def list_repos(self) -> list[RepoInfo]:
        response = await self.client.get("/user/repos", params={"per_page": 100, "sort": "updated"})
        response.raise_for_status()
        repos = response.json()
        return [
            RepoInfo(
                id=str(r["id"]),
                name=r["name"],
                full_name=r["full_name"],
                url=r["clone_url"],
                default_branch=r["default_branch"],
                language=r.get("language"),
                private=r.get("private", False),
            )
            for r in repos
        ]

    async def get_repo(self, name: str) -> RepoInfo | None:
        try:
            response = await self.client.get(f"/repos/{name}")
            response.raise_for_status()
            r = response.json()
            return RepoInfo(
                id=str(r["id"]),
                name=r["name"],
                full_name=r["full_name"],
                url=r["clone_url"],
                default_branch=r["default_branch"],
                language=r.get("language"),
                private=r.get("private", False),
            )
        except httpx.HTTPStatusError:
            return None

    async def create_branch(self, repo: str, name: str, base: str = "main") -> str:
        full_name = f"teammatex/{name}" if not name.startswith("teammatex/") else name

        base_ref = await self.client.get(f"/repos/{repo}/git/ref/heads/{base}")
        base_ref.raise_for_status()
        sha = base_ref.json()["object"]["sha"]

        response = await self.client.post(
            f"/repos/{repo}/git/refs",
            json={"ref": f"refs/heads/{full_name}", "sha": sha},
        )
        response.raise_for_status()
        return full_name

    async def get_file(self, repo: str, path: str, ref: str = "main") -> str | None:
        try:
            response = await self.client.get(
                f"/repos/{repo}/contents/{path}", params={"ref": ref},
            )
            response.raise_for_status()
            import base64
            return base64.b64decode(response.json()["content"]).decode()
        except httpx.HTTPStatusError:
            return None

    async def create_or_update_file(
        self, repo: str, path: str, content: str, message: str, branch: str,
    ) -> dict:
        import base64

        sha = None
        try:
            existing = await self.client.get(
                f"/repos/{repo}/contents/{path}", params={"ref": branch},
            )
            if existing.status_code == 200:
                sha = existing.json().get("sha")
        except Exception:
            pass

        body = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        response = await self.client.put(f"/repos/{repo}/contents/{path}", json=body)
        response.raise_for_status()
        return response.json()

    async def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> PRInfo:
        response = await self.client.post(
            f"/repos/{repo}/pulls",
            json={"title": title, "body": body, "head": head, "base": base},
        )
        response.raise_for_status()
        data = response.json()
        return PRInfo(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            branch=head,
            base=base,
            state=data["state"],
            url=data["html_url"],
            author=data["user"]["login"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )

    async def get_pr(self, repo: str, number: int) -> PRInfo | None:
        try:
            response = await self.client.get(f"/repos/{repo}/pulls/{number}")
            response.raise_for_status()
            data = response.json()
            return PRInfo(
                number=data["number"],
                title=data["title"],
                body=data.get("body"),
                branch=data["head"]["ref"],
                base=data["base"]["ref"],
                state=data["state"],
                url=data["html_url"],
                author=data["user"]["login"],
            )
        except httpx.HTTPStatusError:
            return None

    async def comment_on_pr(self, repo: str, number: int, body: str) -> None:
        response = await self.client.post(
            f"/repos/{repo}/issues/{number}/comments",
            json={"body": body},
        )
        response.raise_for_status()

    async def list_prs(self, repo: str, state: str = "open") -> list[PRInfo]:
        response = await self.client.get(
            f"/repos/{repo}/pulls", params={"state": state},
        )
        response.raise_for_status()
        prs = response.json()
        return [
            PRInfo(
                number=p["number"],
                title=p["title"],
                body=p.get("body"),
                branch=p["head"]["ref"],
                base=p["base"]["ref"],
                state=p["state"],
                url=p["html_url"],
                author=p["user"]["login"],
            )
            for p in prs
        ]

    async def get_pr_diff(self, repo: str, number: int) -> str:
        response = await self.client.get(
            f"/repos/{repo}/pulls/{number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        response.raise_for_status()
        return response.text

    async def get_pr_reviews(self, repo: str, number: int) -> list[dict]:
        response = await self.client.get(f"/repos/{repo}/pulls/{number}/reviews")
        response.raise_for_status()
        return response.json()

    async def get_pr_comments(self, repo: str, number: int) -> list[dict]:
        response = await self.client.get(f"/repos/{repo}/pulls/{number}/comments")
        response.raise_for_status()
        return response.json()

    async def request_reviewers(self, repo: str, number: int, reviewers: list[str]) -> None:
        response = await self.client.post(
            f"/repos/{repo}/pulls/{number}/requested_reviewers",
            json={"reviewers": reviewers},
        )
        response.raise_for_status()

    async def get_commit_status(self, repo: str, ref: str) -> dict:
        response = await self.client.get(
            f"/repos/{repo}/commits/{ref}/status",
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        if not settings.github_webhook_secret:
            return True
        mac = hmac.new(
            settings.github_webhook_secret.encode(),
            payload,
            hashlib.sha256,
        )
        expected = f"sha256={mac.hexdigest()}"
        return hmac.compare_digest(expected, signature)

    @staticmethod
    async def handle_webhook(event: str, payload: dict) -> dict | None:
        logger.info("github_webhook", gh_event=event, action=payload.get("action"))

        if event == "pull_request":
            return await GitHubProvider._handle_pr_webhook(payload)
        elif event == "push":
            return await GitHubProvider._handle_push_webhook(payload)
        elif event == "issue_comment":
            return GitHubProvider._handle_comment_webhook(payload)
        elif event == "pull_request_review":
            return GitHubProvider._handle_review_webhook(payload)

        return {"handled": False, "event": event}

    @staticmethod
    async def _handle_pr_webhook(payload: dict) -> dict:
        action = payload.get("action")
        pr = payload.get("pull_request", {})
        return {
            "handled": True,
            "event": "pull_request",
            "action": action,
            "pr_number": pr.get("number"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "merged": pr.get("merged", False),
            "author": pr.get("user", {}).get("login"),
            "repo": payload.get("repository", {}).get("full_name"),
        }

    @staticmethod
    async def _handle_push_webhook(payload: dict) -> dict:
        ref = payload.get("ref", "")
        return {
            "handled": True,
            "event": "push",
            "ref": ref,
            "branch": ref.replace("refs/heads/", ""),
            "commits": len(payload.get("commits", [])),
            "repo": payload.get("repository", {}).get("full_name"),
        }

    @staticmethod
    def _handle_comment_webhook(payload: dict) -> dict:
        issue = payload.get("issue", {})
        return {
            "handled": True,
            "event": "issue_comment",
            "action": payload.get("action"),
            "issue_number": issue.get("number"),
            "comment": (payload.get("comment", {}).get("body", "") or "")[:500],
        }

    @staticmethod
    def _handle_review_webhook(payload: dict) -> dict:
        review = payload.get("review", {})
        return {
            "handled": True,
            "event": "pull_request_review",
            "action": payload.get("action"),
            "state": review.get("state"),
            "pr_number": payload.get("pull_request", {}).get("number"),
        }

    async def close(self):
        await self.client.aclose()


def init_github(token: str | None = None) -> GitHubProvider:
    provider = GitHubProvider(token)
    IntegrationRegistry.register_scm(provider)
    return provider
