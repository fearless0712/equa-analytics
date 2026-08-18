from pathlib import Path
import asyncio
import secrets

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Environment, Settings, get_settings
from app.security.csrf import CsrfProtector
from app.security.rate_limit import InMemoryRateLimiter
from app.web.routes import router

APP_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(
        title="EQUA Analytics",
        debug=app_settings.debug,
        docs_url=None if app_settings.environment.value == "production" else "/docs",
        redoc_url=None,
    )
    application.state.settings = app_settings
    csrf_secret = app_settings.secret_key.get_secret_value().strip() or secrets.token_urlsafe(32)
    application.state.csrf = CsrfProtector(csrf_secret)
    application.state.ai_rate_limiter = InMemoryRateLimiter(limit=3, window_seconds=600)
    application.state.pdf_rate_limiter = InMemoryRateLimiter(limit=5, window_seconds=600)
    application.state.pdf_semaphore = asyncio.Semaphore(1)
    application.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    application.include_router(router)

    def apply_security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        if app_settings.environment is Environment.PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @application.exception_handler(Exception)
    async def internal_error_handler(request, exc):
        return apply_security_headers(
            JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
        )

    @application.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        return apply_security_headers(response)

    return application


app = create_app()
