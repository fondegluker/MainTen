from fastapi import FastAPI

from app.core.config import settings
from app.routers.web import router as web_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
)

# Mount web UI routes
app.include_router(web_router)
