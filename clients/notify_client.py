"""Optional outbound alerting. Posts a short message to ALERT_WEBHOOK_URL — a
Slack or Discord incoming webhook (both accept a JSON body with a "text"/
"content" field) — so problems in the unattended daily sync actually reach you.
No-op when the webhook isn't configured; never raises into the caller."""

from __future__ import annotations

from core import logger
from core.config import settings


def is_configured() -> bool:
    return bool(settings.alert_webhook_url)


def send(text: str) -> bool:
    """Post `text` to the configured webhook. Returns True on a successful
    post, False if not configured or the post failed."""
    url = settings.alert_webhook_url
    if not url:
        logger.info("alert", "ALERT_WEBHOOK_URL not set; skipping alert")
        return False

    import requests

    # "text" is Slack's field; "content" is Discord's — send both so one
    # webhook URL works for either service.
    payload = {"text": text, "content": text}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("alert", "alert sent")
        return True
    except Exception as exc:
        logger.error("alert", "failed to send alert", {"error": str(exc)})
        return False
