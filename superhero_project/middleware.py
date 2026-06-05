"""Custom ASGI middlewares."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp
from starlette.types import Message
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send


class SecurityHeadersMiddleware:
    """Inject security response headers on every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        """Store the wrapped ASGI app."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass non-HTTP scopes through; inject headers into HTTP responses."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self'"
                )
            await send(message)

        await self.app(scope, receive, send_with_headers)
