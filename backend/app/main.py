import asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import api_title, settings
from app.routers import analogue_v1, catalog, comparison, evidence, evidence_v2, explore, geospatial, health
from app.services import jobs

MAX_BODY_BYTES = 32_768  # the largest legitimate request (discover / evidence compare) is < 2 KB
PRODUCTION = settings.app_env.lower() == "production"

app = FastAPI(
    title=api_title(), description=settings.description, version=settings.app_version,
    docs_url=None if PRODUCTION else "/docs", redoc_url=None if PRODUCTION else "/redoc",
    openapi_url=None if PRODUCTION else "/openapi.json",
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Reject oversized bodies early and attach defensive headers to every response."""

    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
            return JSONResponse(status_code=413, content={"error": {"code": "payload_too_large", "message": f"Request bodies are limited to {MAX_BODY_BYTES} bytes"}})
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "cross-origin")
        if request.url.path.startswith(("/docs", "/redoc")):
            return response  # Swagger UI needs its own scripts in development
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; frame-ancestors 'none'")
        return response


class BoundedBodyMiddleware:
    """Count streamed bytes as well as Content-Length; bound slow request bodies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        try:
            async with asyncio.timeout(15):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > MAX_BODY_BYTES:
                        response = JSONResponse(status_code=413, content={"error": {"code": "payload_too_large", "message": "Request body exceeds limit"}})
                        return await response(scope, receive, send)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            response = JSONResponse(status_code=408, content={"error": {"code": "request_timeout", "message": "Request body timed out"}})
            return await response(scope, receive, send)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, bounded_receive, send)


app.add_middleware(BoundedBodyMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.include_router(health.router, prefix="/api", tags=["system"])
app.include_router(catalog.router, prefix="/api", tags=["catalog"])
app.include_router(comparison.router, prefix="/api", tags=["comparison"])
app.include_router(evidence.router, prefix="/api", tags=["evidence v1 (historical)"])
app.include_router(evidence_v2.router, prefix="/api", tags=["analog evidence v2 (historical)"])
app.include_router(analogue_v1.router, prefix="/api", tags=["analogue method v1.0"])
app.include_router(geospatial.router, prefix="/api", tags=["geospatial provenance"])
app.include_router(explore.router, prefix="/api", tags=["user AOI screening"])


@app.on_event("startup")
def _recover_jobs() -> None:
    jobs.recover_interrupted()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    # Never echo request input back: report location and message only, bounded in size.
    details = [{"loc": [str(part)[:64] for part in error.get("loc", ())][:6], "msg": str(error.get("msg", ""))[:200], "type": error.get("type")}
               for error in exc.errors()[:10]]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Request validation failed", "details": details}})


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)[:300]}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, __: Exception):
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Unexpected server error"}})


@app.get("/")
def root():
    payload = {"service": settings.product_name, "application_id": settings.application_id, "version": settings.app_version, "health": "/api/health"}
    if not PRODUCTION:
        payload["docs"] = "/docs"
    return payload
