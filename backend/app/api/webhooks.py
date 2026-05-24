import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request
from structlog import get_logger

from app.config import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_hmac(secret: str, payload: bytes, signature: str) -> bool:
    if not secret:
        return True
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    expected = f"sha256={mac.hexdigest()}"
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(request: Request):
    event = request.headers.get("X-GitHub-Event", "unknown")
    signature = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()

    from app.services.integrations.github import GitHubProvider
    if not GitHubProvider.verify_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    result = await GitHubProvider.handle_webhook(event, payload)
    logger.info("github_webhook_processed", event=event, result=str(result)[:200])
    return {"received": True, "event": event}


@router.post("/jira")
async def jira_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature", "")
    if settings.jira_api_token:
        if not _verify_hmac(settings.jira_api_token, body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    from app.services.integrations.jira import JiraProvider
    result = await JiraProvider.handle_webhook(payload)
    logger.info("jira_webhook_processed", result=str(result)[:200])
    return {"received": True}


@router.post("/slack")
async def slack_webhook(request: Request):
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if settings.slack_signing_secret and timestamp and signature:
        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        expected = f"v0={hmac.new(settings.slack_signing_secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()}"
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        event_type = event.get("type", "unknown")
        logger.info("slack_event", type=event_type)

        if event_type == "app_mention":
            text = event.get("text", "")
            channel = event.get("channel", "")
            user = event.get("user", "")
            logger.info("slack_mention_for_agent", channel=channel, user=user, text=text[:200])

    return {"received": True}
