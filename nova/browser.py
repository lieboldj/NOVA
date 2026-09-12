"""Browser authentication: short-lived HttpOnly sessions, never bundled API credentials."""

import secrets

from fastapi import Request, Response
from pydantic import Field, SecretStr
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount, Router
from starlette.staticfiles import StaticFiles

from nova.schemas import StrictModel
from nova.workflow import fail


class Login(StrictModel):
    token: SecretStr = Field(min_length=1, max_length=500)


def browser_actor(request):
    if not request.session.get("reviewer"):
        fail("Reviewer sign-in required", 401)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        expected = request.session.get("csrf", "")
        actual = request.headers.get("x-nova-csrf", "")
        if not expected or not secrets.compare_digest(expected, actual):
            fail("Session verification failed; reload and try again", 403)
    return request.app.state.settings.nova_reviewer_name


def install_browser(app, settings, Reviewer):
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.nova_reviewer_token.get_secret_value(),
        session_cookie=settings.nova_session_cookie,
        max_age=8 * 60 * 60,
        same_site="strict",
        https_only=settings.nova_cookie_secure,
    )

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/session", tags=["Browser"])
    def session(request: Request):
        if not request.session.get("reviewer"):
            return {"authenticated": False}
        return {
            "authenticated": True,
            "reviewer": settings.nova_reviewer_name,
            "csrf": request.session["csrf"],
        }

    @app.post("/session", tags=["Browser"])
    def login(body: Login, request: Request):
        # Same-origin JSON login prevents another site from replacing the reviewer's session.
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            fail("Sign in from the NOVA portal", 403)
        expected = settings.nova_reviewer_token.get_secret_value()
        if not expected or not secrets.compare_digest(body.token.get_secret_value(), expected):
            fail("Invalid reviewer access key", 401)
        request.session.clear()
        request.session.update(reviewer=True, csrf=secrets.token_urlsafe(32))
        return session(request)

    @app.delete("/session", tags=["Browser"], status_code=204)
    def logout(request: Request, actor: Reviewer):
        request.session.clear()
        return Response(status_code=204)

    # Both /api/* for the portal and the existing unprefixed automation API remain available.
    app.router.routes.append(Mount("/api", app=Router(routes=list(app.router.routes))))
    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
