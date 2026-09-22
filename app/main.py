from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse

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

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # For HTML requests that are unauthenticated, redirect to login page
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        accept = request.headers.get("accept", "")
        if "text/html" in accept or not accept:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    # Default behavior for non-HTML/API calls
    from fastapi.exception_handlers import http_exception_handler as default_handler
    return await default_handler(request, exc)

# Mount web UI, admin, and import routers
app.include_router(web_router)
app.include_router(admin_router)
app.include_router(import_router)
