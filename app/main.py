from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.jobs import router as jobs_router
from app.api.routes.plugins import router as plugins_router
from app.api.routes.resume_profiles import router as resume_profiles_router
from app.api.routes.ui import router as ui_router


app = FastAPI(title="Job Assist API")
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
app.include_router(ui_router)
app.include_router(jobs_router)
app.include_router(plugins_router)
app.include_router(resume_profiles_router)
