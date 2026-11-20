"""
CSRF defence for cookie-based sessions: reject state-changing requests whose Origin header
names a site we don't trust. Browsers always send Origin on cross-site POSTs, and a malicious
page can't forge it. Requests without an Origin (curl, scripts) aren't browser-driven CSRF and
pass; they still need a valid session cookie.

This works together with SameSite=Lax cookies and a strict CORS allow-list.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def make_origin_guard(allowed_origins: set[str]) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def origin_guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in allowed_origins:
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        return await call_next(request)

    return origin_guard