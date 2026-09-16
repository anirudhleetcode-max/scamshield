import logging
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
from .services.classifier import get_model

log = logging.getLogger("scamshield")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    await run_in_threadpool(get_model)  # load the joblib model once
    yield
    await close_client()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_body(request: Request, call_next):
    size = request.headers.get("content-length")
    if size and size.isdigit() and int(size) > settings.max_body_bytes:
        return JSONResponse({"detail": "Request body too large", "status": 413}, status_code=413)
    return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail, "status": exc.status_code}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse({"detail": errors, "status": 422}, status_code=422)


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse({"detail": "Something went wrong on our side", "status": 500}, status_code=500)


app.include_router(auth.router)
app.include_router(check.router)
app.include_router(lookup.router)
app.include_router(reports.router)
app.include_router(insights.router)


@app.get("/api/health")
async def health():
    await get_db().command("ping")
    return {"status": "ok", "db": "connected", "model": get_model().version}
