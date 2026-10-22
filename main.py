"""QuantiPro API — SPSS processing microservice powered by QuantipyMRX + Haiku."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from auth import init_key_registry
from config import get_settings
from middleware.idempotency import IdempotencyMiddleware
from middleware.response_headers import ResponseHeadersMiddleware
from middleware.usage_logger import UsageLoggerMiddleware
from middleware.usage_metering import UsageMeteringMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    settings = get_settings()
    logger.info("Starting %s v%s (%s)", settings.app_name, settings.app_version, settings.app_env)

    # Load API keys into memory
    init_key_registry()

    if settings.auth_disabled:
        logger.warning(
            "AUTH_DISABLED=true — requests without an Authorization header are served as "
            "'anonymous' with all scopes (env=%s). Testing only; unset to restore auth.",
            settings.app_env,
        )

    # Validate Anthropic key presence (warn, don't crash — Haiku features will be disabled)
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — ticket parsing and smart labeling will be disabled")

    # Start MCP Redis relay for cross-replica SSE session routing
    from mcp_server import start_redis_relay, stop_redis_relay
    await start_redis_relay()

    yield

    await stop_redis_relay()
    logger.info("Shutting down %s", settings.app_name)


def create_application() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "**Indico Crosstab API** — REST API for processing SPSS (.sav) files.\n\n"
            "Powered by QuantipyMRX for market research analysis: crosstabs with significance testing, "
            "auto-detection of question types, NPS, Top/Bottom Box, nets, and AI-powered "
            "Reporting Ticket parsing via Claude Haiku.\n\n"
            "## Authentication\n"
            "All endpoints require `Authorization: Bearer sk_live_...` or `sk_test_...`\n\n"
            "## Rate Limits\n"
            "| Plan | Requests/min | Max file size |\n"
            "|------|-------------|---------------|\n"
            "| Free (sk_test_) | 10 | 5 MB |\n"
            "| Pro | 60 | 50 MB |\n"
            "| Business | 200 | 200 MB |\n"
        ),
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "System", "description": "Health check and system info"},
            {"name": "Metadata", "description": "Extract variable metadata from SPSS files"},
            {"name": "Analysis", "description": "Frequency, crosstab, NPS, and other analyses"},
            {"name": "Processing", "description": "Full pipeline: upload + analyze + return results"},
            {"name": "Conversion", "description": "Convert SPSS files to other formats"},
            {"name": "AI Features", "description": "Haiku-powered ticket parsing and smart labeling"},
        ],
    )

    # Middleware stack (outermost first):
    # 1. Usage logger — logs every authenticated request for billing
    # 2. CORS — allow cross-origin requests
    app.add_middleware(UsageMeteringMiddleware)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(ResponseHeadersMiddleware)
    app.add_middleware(UsageLoggerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "API-Version", "X-RateLimit-Limit",
                        "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    )

    # Standardized error handlers using shared.response.error_response
    from shared.response import error_response

    @app.exception_handler(asyncio.TimeoutError)
    async def timeout_handler(request: Request, exc: asyncio.TimeoutError):
        logger.warning("Processing timeout [%s]", getattr(request.state, "request_id", ""))
        return JSONResponse(status_code=504, content=error_response(
            "PROCESSING_TIMEOUT",
            f"Processing exceeded {settings.processing_timeout_seconds}s limit. Try a smaller file or fewer stubs.",
        ))

    @app.exception_handler(RuntimeError)
    async def runtime_error_handler(request: Request, exc: RuntimeError):
        if "too many files" in str(exc).lower():
            logger.warning("Concurrency limit [%s]: %s", getattr(request.state, "request_id", ""), exc)
            return JSONResponse(status_code=503, content=error_response(
                "SERVER_BUSY", str(exc),
            ), headers={"Retry-After": "5"})
        return await global_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception [%s]: %s", getattr(request.state, "request_id", ""), exc, exc_info=True)
        return JSONResponse(status_code=500, content=error_response(
            "PROCESSING_FAILED",
            "Internal server error" if settings.is_production else str(exc),
        ))

    # OAuth 2.0 discovery endpoints (RFC 9728)
    @app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
    async def oauth_protected_resource():
        """RFC 9728 Protected Resource Metadata — tells Claude.ai where to find the auth server."""
        clerk_url = settings.clerk_frontend_api
        return {
            "resource": settings.base_url,
            "authorization_servers": [clerk_url] if clerk_url else [],
            "scopes_supported": ["openid", "profile", "email"],
            "bearer_methods_supported": ["header"],
        }

    # Register routers
    from routers.health import router as health_router
    from routers.metadata import router as metadata_router
    from routers.frequency import router as frequency_router
    from routers.crosstab import router as crosstab_router
    from routers.convert import router as convert_router
    from routers.parse_ticket import router as parse_ticket_router
    from routers.process import router as process_router
    from routers.tabulate import router as tabulate_router
    from routers.correlation import router as correlation_router
    from routers.anova import router as anova_router
    from routers.gap_analysis import router as gap_router
    from routers.satisfaction import router as satisfaction_router
    from routers.auto_analyze import router as auto_analyze_router
    from routers.downloads import router as downloads_router
    from routers.file_upload import router as file_upload_router
    from routers.weight import router as weight_router
    from routers.chat import router as chat_router
    from routers.chat_stream import router as chat_stream_router
    from routers.wave_compare import router as wave_compare_router
    from routers.keys import router as keys_router
    from routers.smart_spec import router as smart_spec_router
    from routers.library import router as library_router
    from routers.codebook import router as codebook_router
    from routers.setups import router as setups_router
    from routers.exports import router as exports_router
    from routers.ui_auth import router as ui_auth_router

    app.include_router(health_router)
    app.include_router(metadata_router)
    app.include_router(frequency_router)
    app.include_router(crosstab_router)
    app.include_router(convert_router)
    app.include_router(parse_ticket_router)
    app.include_router(process_router)
    app.include_router(tabulate_router)
    app.include_router(correlation_router)
    app.include_router(anova_router)
    app.include_router(gap_router)
    app.include_router(satisfaction_router)
    app.include_router(auto_analyze_router)
    app.include_router(downloads_router)
    app.include_router(file_upload_router)
    app.include_router(weight_router)
    if settings.enable_ai_chat:
        app.include_router(chat_router)
        app.include_router(chat_stream_router)
    app.include_router(wave_compare_router)
    app.include_router(keys_router)
    app.include_router(smart_spec_router)
    if settings.enable_datasets:
        app.include_router(library_router)
    app.include_router(codebook_router)
    app.include_router(setups_router)
    app.include_router(exports_router)
    app.include_router(ui_auth_router)

    from routers.jobs import router as jobs_router
    app.include_router(jobs_router)

    # MCP server — SSE transport
    # NOTE: Streamable HTTP (http_app) CANNOT be mounted as FastAPI sub-app —
    # it requires run() to initialize an anyio task group, which doesn't happen
    # when mounted. See Railway logs: "Task group is not initialized."
    # Streamable HTTP requires running FastMCP as standalone server, not embedded.
    # When FastMCP fixes this, re-enable at /mcp with http_app(path="/").
    from mcp_server import get_mcp_asgi_app
    app.mount("/mcp", get_mcp_asgi_app())
    logger.info("MCP SSE mounted at /mcp/sse")

    # NOTE: SSE deprecation header REMOVED — middleware breaks SSE streaming responses.
    # Deprecation will be communicated via spss_get_server_info tool response instead.

    # Demo key injection — served as JS so the key isn't in the git repo
    @app.get("/static/config.js", include_in_schema=False)
    async def demo_config():
        demo_key = settings.demo_api_key or "demo"
        from starlette.responses import Response
        features = json.dumps({"datasets": settings.enable_datasets, "chat": settings.enable_ai_chat})
        return Response(
            content=f"window.__INDICO_CROSSTAB_DEMO_KEY__ = '{demo_key}';\nwindow.__INDICO_FEATURES__ = {features};",
            media_type="application/javascript",
        )

    # Serve frontend + static pages
    public_dir = Path(__file__).parent / "public"
    # Pages are revalidated on every load (cheap 304 via ETag) so a deploy is seen straight away;
    # without this, browsers heuristically cache the HTML and keep running old page code.
    PAGE_HEADERS = {"Cache-Control": "no-cache"}
    if public_dir.exists():
        from urllib.parse import quote

        from fastapi.responses import RedirectResponse

        from routers.ui_auth import session_email

        def page(name: str):
            return FileResponse(public_dir / name, headers=PAGE_HEADERS)

        def signed_in_page(name: str):
            """App pages need a signed-in session; otherwise go to sign-in and come back."""
            async def handler(request: Request):
                if not session_email(request):
                    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
                    return RedirectResponse(f"/?next={quote(target, safe='')}", status_code=303)
                return page(name)
            return handler

        # Sign-in (split screen) — signed-in visitors go straight to the app
        async def sign_in(request: Request):
            if session_email(request):
                return RedirectResponse("/app", status_code=303)
            return page("login.html")

        app.add_api_route("/", sign_in, methods=["GET"], include_in_schema=False)
        app.add_api_route("/login", sign_in, methods=["GET"], include_in_schema=False)

        # App pages. The app is one stepped flow (/app: Dataset → Variables → …) under one app bar;
        # /review is its Variables step (embedded), the rest are off the bar but still served.
        app_pages = {
            "/review": "review.html",
            "/app": "app.html",
            "/export": "app.html",
            "/express": "express.html",
            "/wizard": "wizard.html",
            "/export-mcp": "chat.html",
            "/settings": "settings.html",
        }
        if not settings.enable_ai_chat:
            del app_pages["/export-mcp"]
        for path, name in app_pages.items():
            app.add_api_route(path, signed_in_page(name), methods=["GET"], include_in_schema=False)

        # Old sections now live in the flow: Home and Workflows open it, Datasets is its first step
        def to_app():
            async def handler(request: Request):
                return RedirectResponse("/app", status_code=303)
            return handler
        old_pages = ["/home", "/workflows"]
        if settings.enable_datasets:
            old_pages += ["/datasets", "/datasets/upload", "/datasets/{library_id}"]
        for path in old_pages:
            app.add_api_route(path, to_app(), methods=["GET"], include_in_schema=False)

        # Public pages: the MCP file uploader (linked from Claude) and docs
        public_pages = {"/upload": "upload.html", "/privacy": "privacy.html", "/docs/mcp": "mcp-docs.html"}
        for path, name in public_pages.items():
            app.add_api_route(path, (lambda n: lambda: page(n))(name), methods=["GET"], include_in_schema=False)

        class AssetFiles(StaticFiles):
            """Shared assets only: pages are served by the routes above (so sign-in applies)."""
            async def get_response(self, path, scope):
                if path.endswith(".html"):
                    return JSONResponse(status_code=404, content={"detail": "Not Found"})
                response = await super().get_response(path, scope)
                response.headers.update(PAGE_HEADERS)  # revalidate shared CSS/JS like the pages
                return response

        app.mount("/static", AssetFiles(directory=str(public_dir)), name="static")
    else:
        @app.get("/", include_in_schema=False)
        async def root():
            return {"name": settings.app_name, "version": settings.app_version, "docs": "/docs"}

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=not settings.is_production,
    )
