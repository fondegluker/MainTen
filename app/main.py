from fastapi import FastAPI

from app.core.config import settings
from app.routers.admin import router as admin_router
from app.routers.import_fleet import router as import_router
from app.routers.web import router as web_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
)

# Mount web UI, admin, and import routers
app.include_router(web_router)
app.include_router(admin_router)
app.include_router(import_router)
