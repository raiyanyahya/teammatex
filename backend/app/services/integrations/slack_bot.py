import json
import aiohttp
from structlog import get_logger

from app.config import settings

logger = get_logger(__name__)


class SlackBot:
    def __init__(self):
        self.token = settings.slack_bot_token
        self.enabled = bool(self.token)
        self._http: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._http is None:
            self._http = aiohttp.ClientSession()
        return self._http

    async def post_message(self, channel: str, text: str, thread_ts: str | None = None) -> dict:
        if not self.enabled:
            return {"error": "Slack bot token not configured"}
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts

        try:
            async with session.post("https://slack.com/api/chat.postMessage",
                                     headers=headers, json=payload, timeout=10) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    logger.warning("slack_post_failed", error=result.get("error"))
                return result
        except Exception as e:
            logger.error("slack_post_error", error=str(e))
            return {"error": str(e)}

    async def post_code_review(self, channel: str, review: dict, pr_url: str = "") -> dict:
        if not self.enabled:
            return {"skipped": True}

        blocks = []
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": f"Code Review — {review.get('repo', '')}"},
        })
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": review.get("summary", "")},
        })

        for issue in review.get("issues", [])[:10]:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*[{issue.get('severity', 'low').upper()}]* {issue.get('message')} — `{issue.get('file', '')}`",
                },
            })

        if pr_url:
            blocks.append({
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View PR"},
                    "url": pr_url,
                }],
            })

        session = await self._get_session()
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            async with session.post("https://slack.com/api/chat.postMessage",
                                     headers=headers, json={"channel": channel, "blocks": blocks}, timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.error("slack_review_error", error=str(e))
            return {"error": str(e)}

    async def answer_question(self, channel: str, user: str, question: str) -> str:
        if not self.enabled:
            return "Slack bot not enabled."

        from litellm import acompletion
        from app.services.llm.provider import LLMProvider
        from app.services.agent.rag import RAGPipeline

        rag = RAGPipeline()
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session
            from app.models.repo import Repo
            from sqlalchemy import select

            engine = create_engine(settings.database_url.replace("+asyncpg", "+psycopg2"))
            repo_name = ""
            repo_id = ""
            try:
                with Session(engine) as db:
                    repos = db.execute(select(Repo).where(Repo.is_active == True).limit(5)).scalars().all()
                    repo_name = repos[0].local_name if repos else ""
                    repo_id = str(repos[0].id) if repos else ""
            finally:
                engine.dispose()

            context = await rag.retrieve_context(None, question, repo_id)
        except Exception:
            context = ""

        providers = await LLMProvider._get_available_providers()
        for provider, model, key in providers:
            try:
                actual_model = "deepseek/deepseek-chat" if provider == "deepseek" else f"{provider}/{model}"
                resp = await acompletion(
                    model=actual_model,
                    messages=[
                        {"role": "system", "content": f"You are TeammateX. Answer concisely based on the codebase. Context:\n{context}"},
                        {"role": "user", "content": f"User {user} asks: {question}"},
                    ],
                    api_key=key, temperature=0.3, max_tokens=1000,
                )
                answer = resp.choices[0].message.content or ""
                if answer:
                    await self.post_message(channel, answer)
                return answer
            except Exception:
                continue

        return ""


slack_bot = SlackBot()
