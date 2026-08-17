import base64
import hashlib
import hmac
import secrets
import time

from fastapi import Form, Header, HTTPException, Request
from starlette.responses import Response

CSRF_COOKIE_NAME = "equa_csrf"
CSRF_TTL_SECONDS = 60 * 60


class CsrfProtector:
    def __init__(self, secret: str, *, ttl_seconds: int = CSRF_TTL_SECONDS) -> None:
        self._secret = secret.encode()
        self._ttl = ttl_seconds

    def issue(self, *, now: int | None = None) -> str:
        timestamp = str(now if now is not None else int(time.time()))
        nonce = secrets.token_urlsafe(24)
        content = f"{timestamp}.{nonce}"
        signature = hmac.new(self._secret, content.encode(), hashlib.sha256).digest()
        encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return f"{content}.{encoded}"

    def validate(self, token: str | None, *, now: int | None = None) -> bool:
        if not token:
            return False
        try:
            timestamp_text, nonce, signature = token.split(".", 2)
            timestamp = int(timestamp_text)
        except (TypeError, ValueError):
            return False
        current = now if now is not None else int(time.time())
        if timestamp > current + 60 or current - timestamp > self._ttl:
            return False
        content = f"{timestamp_text}.{nonce}"
        expected = base64.urlsafe_b64encode(
            hmac.new(self._secret, content.encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        return hmac.compare_digest(signature, expected)


def set_csrf_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=CSRF_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


async def require_csrf(
    request: Request,
    csrf_token: str | None = Form(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> None:
    submitted = x_csrf_token or csrf_token
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    protector: CsrfProtector = request.app.state.csrf
    if not submitted or not cookie or not hmac.compare_digest(submitted, cookie) or not protector.validate(submitted):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
