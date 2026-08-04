import httpx
from structlog import get_logger

from app.config import settings
from app.services.integrations.base import (
    ChannelInfo,
    ChatProvider,
    IntegrationRegistry,
)

logger = get_logger(__name__)


class SlackProvider(ChatProvider):
    provider_name = "slack"
    BASE_URL = "https://slack.com/api"

    def __init__(self, token: str | None = None):
        self.token = token or settings.slack_bot_token
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=15,
        )
        self._user_cache: dict[str, dict] = {}
        self._user_cache_max = 200

    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: list | None = None,
    ) -> str:
        body: dict = {"channel": channel, "text": text}
        if blocks:
            body["blocks"] = blocks

        response = await self.client.post("/chat.postMessage", json=body)
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack error: {data.get('error')}")
        return data.get("ts", "")

    async def send_dm(self, user_email: str, text: str) -> str:
        user_id = await self._get_user_id(user_email)
        if not user_id:
            raise ValueError(f"User not found: {user_email}")

        channel_response = await self.client.post(
            "/conversations.open",
            json={"users": user_id},
        )
        channel_data = channel_response.json()
        channel = channel_data.get("channel", {}).get("id", user_id)

        return await self.send_message(channel, text)

    async def _get_user_id(self, email: str) -> str | None:
        if email in self._user_cache:
            return self._user_cache[email].get("id")

        response = await self.client.get(
            "/users.lookupByEmail",
            params={"email": email},
        )
        data = response.json()
        if data.get("ok") and data.get("user"):
            self._user_cache[email] = data["user"]
            return data["user"]["id"]
        return None

    async def list_channels(self) -> list[ChannelInfo]:
        response = await self.client.get(
            "/conversations.list",
            params={"types": "public_channel,private_channel", "limit": 100},
        )
        data = response.json()
        channels = data.get("channels", [])
        return [
            ChannelInfo(
                id=c["id"],
                name=c["name"],
                is_private=c.get("is_private", False),
            )
            for c in channels
        ]

    async def add_reaction(self, channel: str, timestamp: str, emoji: str) -> None:
        await self.client.post(
            "/reactions.add",
            json={"channel": channel, "name": emoji, "timestamp": timestamp},
        )

    async def post_standup(self, channel: str, summary: dict) -> str:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🤖 {settings.teammate_name} — Daily Standup",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Yesterday:*\n{summary.get('yesterday', 'Nothing to report.')}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Today:*\n{summary.get('today', 'No planned tasks.')}",
                },
            },
        ]

        if summary.get("blockers"):
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Blockers:*\n{summary['blockers']}",
                    },
                }
            )

        if summary.get("prs"):
            pr_text = "\n".join(
                f"• <{p.get('url')}|{p.get('title')}> — `{p.get('status')}`" for p in summary["prs"]
            )
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*Active PRs:*\n{pr_text}"}}
            )

        return await self.send_message(channel, "", blocks)

    async def post_pr_summary(self, channel: str, pr: dict) -> str:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🔀 New PR: {pr.get('title', 'Untitled')}"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Branch:* `{pr.get('branch')}` → `{pr.get('base', 'main')}`\n"
                        f"*Files:* {pr.get('files_changed', '?')} changed\n"
                        f"*URL:* <{pr.get('url')}|View on GitHub>"
                    ),
                },
            },
        ]

        if pr.get("summary"):
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": pr["summary"][:3000]},
                }
            )

        return await self.send_message(channel, "", blocks)

    async def post_notification(
        self, channel: str, title: str, message: str, level: str = "info"
    ) -> str:
        emoji_map = {"info": "ℹ️", "warning": "⚠️", "error": "🚨", "success": "✅"}
        emoji = emoji_map.get(level, "ℹ️")
        return await self.send_message(channel, f"{emoji} *{title}*\n{message}")

    async def close(self):
        await self.client.aclose()


def init_slack(token: str | None = None) -> SlackProvider:
    provider = SlackProvider(token)
    IntegrationRegistry.register_chat(provider)
    return provider
