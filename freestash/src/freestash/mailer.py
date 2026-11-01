"""Outgoing email (password resets). Sends through Resend when RESEND_API_KEY is set.

Logs never carry the recipient or the body: a reset body holds a live link, so log access would be account
takeover. The dev server opts in to seeing unsent bodies with FREESTASH_LOG_EMAILS.
"""

from __future__ import annotations

import logging

import httpx

from freestash.config import Settings

log = logging.getLogger("freestash.mail")


async def send_email(settings: Settings, to: str, subject: str, text: str) -> bool:
    if not settings.resend_api_key:
        if settings.log_emails:
            log.warning("Email not sent (no RESEND_API_KEY). Subject: %s\n%s", subject, text)
        else:
            log.warning("Email not sent: RESEND_API_KEY is not set. Subject: %s", subject)
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://api.resend.com/emails",
                              headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                              json={"from": settings.email_from, "to": [to], "subject": subject, "text": text})
    if r.status_code >= 400:
        log.error("Resend rejected an email (HTTP %s). Subject: %s", r.status_code, subject)
        return False
    return True
