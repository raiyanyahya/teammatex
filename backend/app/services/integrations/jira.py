import base64

import httpx
from structlog import get_logger

from app.config import settings
from app.services.integrations.base import (
    BoardInfo,
    IntegrationRegistry,
    IssueInfo,
    ProjectMgmtProvider,
    SprintInfo,
)

logger = get_logger(__name__)


class JiraProvider(ProjectMgmtProvider):
    provider_name = "jira"

    def __init__(self, url: str | None = None, email: str | None = None, token: str | None = None):
        self.base_url = (url or settings.jira_url).rstrip("/")
        self.email = email or settings.jira_email
        self.token = token or settings.jira_api_token

        auth = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
        self.client = httpx.AsyncClient(
            base_url=f"{self.base_url}/rest/api/3",
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
            },
            timeout=30,
        )

    async def list_projects(self) -> list[dict]:
        response = await self.client.get("/project")
        response.raise_for_status()
        return [{"key": p["key"], "name": p["name"], "id": p["id"]} for p in response.json()]

    async def list_boards(self, project_key: str) -> list[BoardInfo]:
        response = await self.client.get(
            "../agile/1.0/board",
            params={"projectKeyOrId": project_key},
        )
        response.raise_for_status()
        return [
            BoardInfo(id=str(b["id"]), name=b["name"], project=project_key)
            for b in response.json().get("values", [])
        ]

    async def list_issues(self, project_key: str, sprint_id: str | None = None) -> list[IssueInfo]:
        jql = f"project = {project_key}"
        if sprint_id:
            jql += f" AND sprint = {sprint_id}"
        jql += " ORDER BY updated DESC"

        response = await self.client.get(
            "/search",
            params={
                "jql": jql,
                "maxResults": 50,
                "fields": "summary,status,assignee,priority,description,sprint",
            },
        )
        response.raise_for_status()
        issues = response.json().get("issues", [])
        return [
            IssueInfo(
                key=i["key"],
                title=i["fields"].get("summary", ""),
                description=(i["fields"].get("description") or "")[:1000],
                status=i["fields"].get("status", {}).get("name", ""),
                assignee=(i["fields"].get("assignee") or {}).get("displayName"),
                priority=(i["fields"].get("priority") or {}).get("name"),
                sprint=(
                    (i["fields"].get("sprint") or {}).get("name")
                    if i["fields"].get("sprint")
                    else None
                ),
                url=f"{self.base_url}/browse/{i['key']}",
            )
            for i in issues
        ]

    async def get_issue(self, key: str) -> IssueInfo | None:
        try:
            response = await self.client.get(f"/issue/{key}")
            response.raise_for_status()
            i = response.json()
            fields = i.get("fields", {})
            return IssueInfo(
                key=i["key"],
                title=fields.get("summary", ""),
                description=(fields.get("description") or "")[:2000],
                status=fields.get("status", {}).get("name", ""),
                assignee=(fields.get("assignee") or {}).get("displayName"),
                priority=(fields.get("priority") or {}).get("name"),
                sprint=None,
                url=f"{self.base_url}/browse/{i['key']}",
            )
        except httpx.HTTPStatusError:
            return None

    async def update_issue(self, key: str, fields: dict) -> None:
        body = {"fields": {}}
        if "status" in fields:
            transitions = await self._get_transitions(key)
            target = fields["status"].lower()
            for t in transitions:
                if t["name"].lower() == target or t["id"] == fields.get("status_id"):
                    body["transition"] = {"id": t["id"]}
                    break

        if "summary" in fields:
            body["fields"]["summary"] = fields["summary"]
        if "description" in fields:
            body["fields"]["description"] = fields["description"]
        if "assignee" in fields:
            body["fields"]["assignee"] = {"name": fields["assignee"]}

        if body.get("fields") or body.get("transition"):
            endpoint = "/issue/{}/transitions" if "transition" in body else "/issue/{}"
            response = await self.client.put(
                endpoint.format(key),
                json=body,
            )
            response.raise_for_status()

    async def _get_transitions(self, key: str) -> list[dict]:
        response = await self.client.get(f"/issue/{key}/transitions")
        response.raise_for_status()
        return [{"id": t["id"], "name": t["name"]} for t in response.json().get("transitions", [])]

    async def comment_on_issue(self, key: str, body: str) -> None:
        response = await self.client.post(
            f"/issue/{key}/comment",
            json={"body": body},
        )
        response.raise_for_status()

    async def list_sprints(self, board_id: str) -> list[SprintInfo]:
        response = await self.client.get(
            f"../agile/1.0/board/{board_id}/sprint",
            params={"maxResults": 50},
        )
        response.raise_for_status()
        return [
            SprintInfo(
                id=str(s["id"]),
                name=s["name"],
                state=s["state"],
                start_date=s.get("startDate"),
                end_date=s.get("endDate"),
            )
            for s in response.json().get("values", [])
        ]

    async def get_active_sprint(self, board_id: str) -> SprintInfo | None:
        sprints = await self.list_sprints(board_id)
        for s in sprints:
            if s.state == "active":
                return s
        return None

    async def get_sprint_issues(self, sprint_id: str) -> list[IssueInfo]:
        response = await self.client.get(
            "/search",
            params={
                "jql": f"sprint = {sprint_id}",
                "maxResults": 100,
                "fields": "summary,status,assignee,priority",
            },
        )
        response.raise_for_status()
        issues = response.json().get("issues", [])
        return [
            IssueInfo(
                key=i["key"],
                title=i["fields"].get("summary", ""),
                description="",
                status=i["fields"].get("status", {}).get("name", ""),
                assignee=(i["fields"].get("assignee") or {}).get("displayName"),
                priority=(i["fields"].get("priority") or {}).get("name"),
                sprint=str(sprint_id),
                url=f"{self.base_url}/browse/{i['key']}",
            )
            for i in issues
        ]

    @staticmethod
    async def handle_webhook(payload: dict) -> dict | None:
        event = payload.get("webhookEvent", "")
        logger.info("jira_webhook", jira_event=event)

        if event == "jira:issue_updated":
            issue = payload.get("issue", {})
            return {
                "handled": True,
                "event": "issue_updated",
                "key": issue.get("key"),
                "summary": issue.get("fields", {}).get("summary"),
                "status": issue.get("fields", {}).get("status", {}).get("name"),
            }
        elif event == "sprint_started":
            sprint = payload.get("sprint", {})
            return {
                "handled": True,
                "event": "sprint_started",
                "sprint_name": sprint.get("name"),
                "sprint_id": sprint.get("id"),
            }
        elif event == "sprint_closed":
            sprint = payload.get("sprint", {})
            return {
                "handled": True,
                "event": "sprint_closed",
                "sprint_name": sprint.get("name"),
            }

        return {"handled": False, "event": event}

    async def close(self):
        await self.client.aclose()


def init_jira(
    url: str | None = None, email: str | None = None, token: str | None = None
) -> JiraProvider:
    provider = JiraProvider(url, email, token)
    IntegrationRegistry.register_pm(provider)
    return provider
