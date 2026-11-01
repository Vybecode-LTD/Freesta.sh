"""Outgoing email (password resets), over SMTP from our own mailbox (decision 0002: Spacemail, implicit TLS on 465).

Logs never carry the recipient or the body: a reset body holds a live link, so log access would be account
takeover. SMTP errors can echo the address back, so only the error's type and code are logged. The dev server
opts in to seeing unsent bodies with FREESTASH_LOG_EMAILS.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from freestash.config import Settings

log = logging.getLogger("freestash.mail")


async def send_email(settings: Settings, to: str, subject: str, text: str) -> bool:
    if not (settings.smtp_username and settings.smtp_password):
        if settings.log_emails:
            log.warning("Email not sent (no SMTP login). Subject: %s\n%s", subject, text)
        else:
            log.warning("Email not sent: FREESTASH_SMTP_USERNAME / FREESTASH_SMTP_PASSWORD are not set. Subject: %s", subject)
        return False
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(usegmt=True)
    msg["Message-ID"] = make_msgid(domain=parseaddr(settings.email_from)[1].rpartition("@")[2] or None)
    msg.set_content(text)
    try:
        await asyncio.to_thread(_deliver, settings, msg)
    except (smtplib.SMTPException, OSError) as e:  # OSError covers refused, unreachable and timed-out connections
        log.error("SMTP send failed: %s %s. Subject: %s", type(e).__name__, getattr(e, "smtp_code", ""), subject)
        return False
    return True


def _deliver(settings: Settings, msg: EmailMessage) -> None:
    context = ssl.create_default_context()
    user, password = settings.smtp_username or "", settings.smtp_password or ""
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20, context=context) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls(context=context)
            smtp.login(user, password)
            smtp.send_message(msg)
