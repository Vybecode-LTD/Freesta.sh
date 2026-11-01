"""The web app's Content-Security-Policy (decision 0002).

Scripts run only from the site itself, plus the inline theme bootstrap in index.html, allowed by its hash. The web
keeps its session token in localStorage, so stopping injected script is what keeps the token safe (a cookie follows
in its own PR). Results come from ~20 providers, so images, audio and font previews may load from any https host.
"""

from __future__ import annotations

import base64
import hashlib
import re

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", flags=re.S | re.I)


def content_security_policy(index_html: str) -> str:
    hashes = [f"'sha256-{base64.b64encode(hashlib.sha256(body.encode('utf-8')).digest()).decode()}'"
              for body in _INLINE_SCRIPT.findall(index_html)]
    return "; ".join([
        "default-src 'self'",
        " ".join(["script-src 'self'", *hashes]),
        "style-src 'self'",
        "img-src 'self' https: data: blob:",
        "media-src 'self' https:",
        "font-src 'self' https: data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


class SecurityHeaders:
    """Pure ASGI rather than BaseHTTPMiddleware, so streamed search results and background tasks pass untouched."""

    def __init__(self, app: ASGIApp, csp: str) -> None:
        self.app, self.csp = app, csp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).setdefault("content-security-policy", self.csp)
            await send(message)

        await self.app(scope, receive, send_with_headers)
