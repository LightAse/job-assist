from fastapi import FastAPI

from app.api.routes.plugins import router as plugins_router


app = FastAPI(title="Job Assist API")
app.include_router(plugins_router)
