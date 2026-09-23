from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_admin,
)
from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie, verify_magic_link_token
from app.core.database import get_db
from app.core.i18n import get_locale, translate
from app.models.models import (
    Computer,
    MaintenanceEvent,
    MaintenanceEventStatus,
    User,
    UserRole,
)

templates = Jinja2Templates(directory="app/templates")


def context_with_defaults(request: Request, current_user: User = None, extra: dict = None) -> dict:
    ctx = {
        "request": request,
        "current_user": current_user,
        "locale": get_locale(request, current_user.locale if current_user else None),
        "translate": translate,
    }
    if extra:
        ctx.update(extra)
    return ctx


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    if current_user.role == UserRole.ADMIN:
        return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)
    elif current_user.role in (UserRole.TECHNICIAN, UserRole.OBSERVER):
        return RedirectResponse(url="/reports", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/user/my-computers", status_code=status.HTTP_302_FOUND)


@router.get("/set-locale")
def set_locale(locale: str, request: Request, response: Response):
    target_locale = locale if locale in ("ru", "en") else "ru"
    referer = request.headers.get("referer", "/")
    resp = RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)
    resp.set_cookie(key="locale", value=target_locale, httponly=True)
    return resp


@router.get("/auth/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = None, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    if current_user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", context_with_defaults(request, current_user, {"error": error}))


@router.post("/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    provider = LocalAuthProvider()
    from app.auth.base import AuthCredentials

    user = provider.authenticate(db, AuthCredentials(username_or_email=username, password=password))
    if not user:
        return templates.TemplateResponse(
            "login.html",
            context_with_defaults(request, None, {"error": "invalid_credentials"}),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    session_token = generate_session_cookie(user.id)
    resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    resp.set_cookie(key="session", value=session_token, httponly=True, secure=False)
    return resp


@router.get("/auth/magic-link")
def magic_link_login(token: str, request: Request, db: Session = Depends(get_db)):
    data = verify_magic_link_token(token)
    if not data:
        return templates.TemplateResponse(
            "login.html",
            context_with_defaults(request, None, {"error": "invalid_token"}),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    user_id = data.get("user_id")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        return templates.TemplateResponse(
            "login.html",
            context_with_defaults(request, None, {"error": "invalid_token"}),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    session_token = generate_session_cookie(user.id)
    computer_id = data.get("computer_id")
    redirect_url = f"/user/my-computers?computer_id={computer_id}" if computer_id else "/user/my-computers"

    resp = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    resp.set_cookie(key="session", value=session_token, httponly=True, secure=False)
    return resp


@router.get("/auth/logout")
def logout():
    resp = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie(key="session")
    return resp


@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    total_computers = db.query(Computer).count()
    scheduled_events = (
        db.query(MaintenanceEvent).filter(MaintenanceEvent.status == MaintenanceEventStatus.PLANNED).count()
    )
    completed_events = db.query(MaintenanceEvent).filter(MaintenanceEvent.status == MaintenanceEventStatus.DONE).count()
    overdue_events = db.query(MaintenanceEvent).filter(MaintenanceEvent.status == MaintenanceEventStatus.MISSED).count()

    stats = {
        "total_computers": total_computers,
        "scheduled_events": scheduled_events,
        "completed_events": completed_events,
        "overdue_events": overdue_events,
    }

    return templates.TemplateResponse(
        "admin_dashboard.html", context_with_defaults(request, current_user, {"stats": stats})
    )


@router.get("/user/my-computers", response_class=HTMLResponse)
def user_computers(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    computers = db.query(Computer).filter(Computer.owner_user_id == current_user.id).all()
    return templates.TemplateResponse(
        "user_computers.html", context_with_defaults(request, current_user, {"computers": computers})
    )
