"""Outgoing email (password resets). Sends through Resend when RESEND_API_KEY is set; otherwise logs."""

from __future__ import annotations

import logging

import httpx

from freestash.config import Settings

log = logging.getLogger("freestash.mail")


async def send_email(settings: Settings, to: str, subject: str, text: str) -> bool:
    if not settings.resend_api_key:
        log.warning("RESEND_API_KEY not set; email to %s not sent. Subject: %s\n%s", to, subject, text)
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://api.resend.com/emails",
                              headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                              json={"from": settings.email_from, "to": [to], "subject": subject, "text": text})
    if r.status_code >= 400:
        log.error("Resend rejected the email to %s: %s %s", to, r.status_code, r.text[:300])
        return False
    return True
