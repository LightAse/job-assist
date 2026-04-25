import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.jobs import router as jobs_router
from app.api.routes.plugins import router as plugins_router
from app.api.routes.resume_profiles import router as resume_profiles_router
from app.api.routes.settings import router as settings_router
from app.api.routes.ui import router as ui_router


def _parse_csv_env(name: str, *, default: str = "") -> list[str]:
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


logger = logging.getLogger(__name__)
default_extension_origin_regex = r"^(chrome-extension|moz-extension):\/\/.*$"
allowed_origins = _parse_csv_env(
    "JOB_ASSIST_CORS_ALLOWED_ORIGINS",
    default="http://localhost:8080,http://127.0.0.1:8080,http://localhost:8000,http://127.0.0.1:8000",
)
allowed_origin_regex = os.environ.get("JOB_ASSIST_CORS_ALLOWED_ORIGIN_REGEX", default_extension_origin_regex) or None

app = FastAPI(title="Job Assist API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_cors_origin_for_debugging(request: Request, call_next):
    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin and (request.method == "OPTIONS" or response.status_code >= 400):
        logger.info(
            "CORS debug: method=%s path=%s origin=%s status=%s allowed_origins=%s allowed_origin_regex=%s",
            request.method,
            request.url.path,
            origin,
            response.status_code,
            allowed_origins,
            allowed_origin_regex,
        )
    return response


app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
app.include_router(ui_router)
app.include_router(jobs_router)
app.include_router(plugins_router)
app.include_router(resume_profiles_router)
app.include_router(settings_router)
