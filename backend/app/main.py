import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth
from .config import get_settings
from .db import close_client, ensure_indexes, get_db
from .routers import check, insights, lookup, reports
from .services.classifier import ModelUnavailable, load_model, model_status

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("scamshield")
access = logging.getLogger("scamshield.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    await run_in_threadpool(load_model)  # never raises: failures leave the API in a degraded state
    yield
    await close_client()


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan,
              description="Scam / phishing message checker for Indian SMS, WhatsApp and UPI requests.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def limit_and_log(request: Request, call_next):
    start = time.perf_counter()
    size = request.headers.get("content-length")
    if size and size.isdigit() and int(size) > settings.max_body_bytes:
        response = JSONResponse({"detail": "Request body too large", "status": 413}, status_code=413)
    else:
        response = await call_next(request)
    # method, path and status only - never bodies, query strings or message text
    access.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code,
                (time.perf_counter() - start) * 1000)
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail, "status": exc.status_code}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse({"detail": errors, "status": 422}, status_code=422)


@app.exception_handler(ModelUnavailable)
async def model_unavailable(request: Request, exc: ModelUnavailable):
    return JSONResponse({"detail": "Message analysis is unavailable: the model is not loaded. "
                                   "UPI/link checks and reports still work.", "status": 503}, status_code=503)


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong on our side", "status": 500}, status_code=500)


app.include_router(auth.router)
app.include_router(check.router)
app.include_router(lookup.router)
app.include_router(reports.router)
app.include_router(insights.router)


@app.get("/api/health")
async def health():
    await get_db().command("ping")
    m = model_status()
    return {"status": "ok" if m["loaded"] else "degraded", "db": "connected",
            "model": m["version"], "model_loaded": m["loaded"], "model_error": m["error"]}
