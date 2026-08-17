from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from secrets import compare_digest

from fastapi import Header, HTTPException, Request
from starlette.responses import JSONResponse, Response

from packages.common.config import get_settings


class InProcessRateLimiter:
    """Small per-instance guard; production ingress must enforce the same limit globally."""

    def __init__(self, requests_per_minute: int):
        self.limit = requests_per_minute
        self.windows: defaultdict[str, deque[float]] = defaultdict(deque)

    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method != "POST":
            return await call_next(request)
        content_length = int(request.headers.get("content-length", "0") or 0)
        if content_length > 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "request body too large"})
        identity = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self.windows[identity]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit:
            return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})
        window.append(now)
        return await call_next(request)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.environment != "production":
        return
    if settings.api_key is None:
        raise HTTPException(status_code=503, detail="production API key is not configured")
    if x_api_key is None or not compare_digest(x_api_key, settings.api_key.get_secret_value()):
        raise HTTPException(status_code=401, detail="invalid API key")
