from datetime import date, datetime, timezone
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_magic_link_token
from app.core.database import get_db
from app.core.validators import (
    parse_optional_enum,
    parse_optional_int,
    parse_optional_str,
    validate_ip,
    validate_mac,
)
from app.models.models import (
    AuditLog,
    Computer,
    DayKind,
    MaintenanceProtocolItem,
    Setting,
    User,
    UserRole,
    WorkingCalendar,
)
from app.routers.web import context_with_defaults
from app.services.audit_service import log_audit

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/admin", tags=["admin"])

# --- USERS CRUD ---


@router.get("/users", response_class=HTMLResponse)
def list_users(
    request: Request,
    q: Any = Query(None),
    role: Any = Query(None),
    status_filter: Any = Query(None, alias="status"),
    sort_by: str = Query("id"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    message: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User)

    q_str = parse_optional_str(q)
    if q_str:
        search_term = f"%{q_str.lower()}%"
        query = query.filter(
            (func.lower(User.username).like(search_term)) | (func.lower(User.email_or_login).like(search_term))
        )

    role_enum = parse_optional_enum(role, UserRole) if role is not None else None
    if role_enum:
        query = query.filter(User.role == role_enum)

    status_str = parse_optional_str(status_filter)
    if status_str == "active":
        query = query.filter(User.is_active == True)
    elif status_str == "inactive":
        query = query.filter(User.is_active == False)

    # Sorting
    sort_column = getattr(User, sort_by, User.id)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    total_count = query.count()
    total_pages = max(1, ceil(total_count / per_page))
    page = min(page, total_pages)

    users = query.offset((page - 1) * per_page).limit(per_page).all()

    return templates.TemplateResponse(
        "admin/users.html",
        context_with_defaults(
            request,
            current_user,
            {
                "users": users,
                "message": message,
                "search": q,
                "role_filter": role,
                "status_filter": status_filter,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "page": page,
                "total_pages": total_pages,
                "total_count": total_count,
            },
        ),
    )


@router.get("/users/create", response_class=HTMLResponse)
def create_user_form(request: Request, current_user: User = Depends(require_admin)):
    return templates.TemplateResponse(
        "admin/user_form.html", context_with_defaults(request, current_user, {"edit_user": None})
    )


@router.post("/users/create")
def create_user(
    request: Request,
    username: str = Form(...),
    email_or_login: str = Form(...),
    password: str = Form(...),
    role: str = Form("USER"),
    is_active: bool | None = Form(False),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(User)
        .filter(
            (func.lower(User.username) == username.strip().lower())
            | (func.lower(User.email_or_login) == email_or_login.strip().lower())
        )
        .first()
    )
    if existing:
        return templates.TemplateResponse(
            "admin/user_form.html",
            context_with_defaults(
                request,
                current_user,
                {"edit_user": None, "error": "Пользователь с таким именем или email уже существует."},
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    provider = LocalAuthProvider()
    hashed = provider.hash_password(password) if password else None

    role_clean = role.strip().lower() if role else "user"
    user_role = UserRole(role_clean) if role_clean in [r.value for r in UserRole] else UserRole.USER
    new_user = User(
        username=username.strip(),
        email_or_login=email_or_login.strip(),
        password_hash=hashed,
        role=user_role,
        is_active=bool(is_active),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="create_user",
        entity="users",
        entity_id=new_user.id,
        after={
            "username": new_user.username,
            "email_or_login": new_user.email_or_login,
            "role": new_user.role.value,
            "is_active": new_user.is_active,
        },
    )

    return RedirectResponse(url="/admin/users?message=Пользователь+успешно+создан", status_code=status.HTTP_302_FOUND)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
def edit_user_form(
    user_id: int, request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        "admin/user_form.html", context_with_defaults(request, current_user, {"edit_user": user})
    )


@router.post("/users/{user_id}/edit")
def update_user(
    user_id: int,
    request: Request,
    username: str = Form(...),
    email_or_login: str = Form(...),
    password: str | None = Form(None),
    role: str = Form("USER"),
    is_active: bool | None = Form(False),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

    before_state = {
        "username": user.username,
        "email_or_login": user.email_or_login,
        "role": user.role.value,
        "is_active": user.is_active,
    }

    user.username = username.strip()
    user.email_or_login = email_or_login.strip()
    if password and password.strip():
        provider = LocalAuthProvider()
        user.password_hash = provider.hash_password(password.strip())

    role_clean = role.strip().lower() if role else "user"
    if role_clean in [r.value for r in UserRole]:
        user.role = UserRole(role_clean)
    user.is_active = bool(is_active)

    db.commit()

    after_state = {
        "username": user.username,
        "email_or_login": user.email_or_login,
        "role": user.role.value,
        "is_active": user.is_active,
    }

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="update_user",
        entity="users",
        entity_id=user.id,
        before=before_state,
        after=after_state,
    )

    return RedirectResponse(url="/admin/users?message=Данные+пользователя+обновлены", status_code=status.HTTP_302_FOUND)


@router.get("/users/{user_id}/reset-password", response_class=HTMLResponse)
def reset_password_form(
    user_id: int, request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        "admin/reset_password.html", context_with_defaults(request, current_user, {"edit_user": user})
    )


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    new_password: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        provider = LocalAuthProvider()
        user.password_hash = provider.hash_password(new_password.strip())
        db.commit()

        log_audit(db=db, actor_user_id=current_user.id, action="reset_password", entity="users", entity_id=user.id)

    return RedirectResponse(url="/admin/users?message=Пароль+сброшен", status_code=status.HTTP_302_FOUND)


def _get_current_magic_token_version(user_id: int, db: Session) -> int:
    setting = db.query(Setting).filter(Setting.key == f"magic_token_version_{user_id}").first()
    return setting.value_json if setting else 0


def _increment_magic_token_version(user_id: int, db: Session) -> int:
    setting_key = f"magic_token_version_{user_id}"
    setting = db.query(Setting).filter(Setting.key == setting_key).first()
    if setting:
        setting.value_json = (setting.value_json or 0) + 1
    else:
        setting = Setting(key=setting_key, value_json=1)
        db.add(setting)
    db.commit()
    return setting.value_json


@router.get("/users/{user_id}/magic-link", response_class=HTMLResponse)
def get_magic_link(
    user_id: int, request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

    ver = _get_current_magic_token_version(user.id, db)
    token = generate_magic_link_token(user.id, token_version=ver)
    magic_url = f"{request.base_url}auth/magic-link?token={token}"

    return templates.TemplateResponse(
        "admin/magic_link.html",
        context_with_defaults(request, current_user, {"edit_user": user, "magic_url": magic_url}),
    )


@router.post("/users/{user_id}/magic-link/regenerate")
@router.post("/users/{user_id}/magic-link")
def reissue_magic_link(
    user_id: int, request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_ver = _increment_magic_token_version(user.id, db)
    token = generate_magic_link_token(user.id, token_version=new_ver)
    magic_url = f"{request.base_url}auth/magic-link?token={token}"

    log_audit(db=db, actor_user_id=current_user.id, action="reissue_magic_link", entity="users", entity_id=user.id)

    accept = request.headers.get("accept", "")
    if "application/json" in accept or request.headers.get("x-requested-with") == "XMLHttpRequest":
        from datetime import datetime, timezone

        now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S")
        return {
            "magic_url": magic_url,
            "message": "Новая ссылка сгенерирована",
            "timestamp": now_str,
        }

    return templates.TemplateResponse(
        "admin/magic_link.html",
        context_with_defaults(
            request,
            current_user,
            {"edit_user": user, "magic_url": magic_url, "message": "Новая ссылка сгенерирована"},
        ),
    )


@router.post("/users/{user_id}/deactivate")
def deactivate_user(user_id: int, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        before_active = user.is_active
        user.is_active = not user.is_active
        db.commit()

        log_audit(
            db=db,
            actor_user_id=current_user.id,
            action="deactivate_user" if not user.is_active else "activate_user",
            entity="users",
            entity_id=user.id,
            before={"is_active": before_active},
            after={"is_active": user.is_active},
        )

    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)


# --- TECHNICIANS MANAGEMENT ---


@router.get("/technicians", response_class=HTMLResponse)
def list_technicians(
    request: Request,
    message: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN).order_by(User.id.asc()).all()

    # Load daily capacity settings
    capacities = {}
    for tech in technicians:
        setting = db.query(Setting).filter(Setting.key == f"technician_capacity_{tech.id}").first()
        capacities[tech.id] = setting.value_json if setting else 1

    return templates.TemplateResponse(
        "admin/technicians.html",
        context_with_defaults(
            request, current_user, {"technicians": technicians, "capacities": capacities, "message": message}
        ),
    )


@router.post("/technicians/{tech_id}/capacity")
def set_technician_capacity(
    tech_id: int,
    daily_capacity: int = Form(1),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    key = f"technician_capacity_{tech_id}"
    setting = db.query(Setting).filter(Setting.key == key).first()
    before_val = setting.value_json if setting else 1

    if setting:
        setting.value_json = max(1, daily_capacity)
    else:
        setting = Setting(key=key, value_json=max(1, daily_capacity))
        db.add(setting)

    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="update_technician_capacity",
        entity="settings",
        entity_id=tech_id,
        before={"capacity": before_val},
        after={"capacity": max(1, daily_capacity)},
    )

    return RedirectResponse(url="/admin/technicians?message=Дневная+норма+обновлена", status_code=status.HTTP_302_FOUND)


# --- COMPUTERS CRUD ---


@router.get("/computers", response_class=HTMLResponse)
def list_computers(
    request: Request,
    q: Any = Query(None),
    location: Any = Query(None),
    rtc: Any = Query(None),
    owner_id: Any = Query(None),
    sort_by: str = Query("hostname"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    message: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Computer)

    q_str = parse_optional_str(q)
    if q_str:
        search_term = f"%{q_str.lower()}%"
        query = query.filter(
            (func.lower(Computer.hostname).like(search_term)) | (func.lower(Computer.ip).like(search_term))
        )

    loc_str = parse_optional_str(location)
    if loc_str:
        query = query.filter(func.lower(Computer.location).like(f"%{loc_str.lower()}%"))

    rtc_str = parse_optional_str(rtc)
    if rtc_str == "yes":
        query = query.filter(Computer.is_round_the_clock == True)
    elif rtc_str == "no":
        query = query.filter(Computer.is_round_the_clock == False)

    parsed_owner_id = parse_optional_int(owner_id)
    if parsed_owner_id is not None:
        query = query.filter(Computer.owner_user_id == parsed_owner_id)

    # Sorting
    sort_column = getattr(Computer, sort_by, Computer.hostname)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    total_count = query.count()
    total_pages = max(1, ceil(total_count / per_page))
    page = min(page, total_pages)

    computers = query.offset((page - 1) * per_page).limit(per_page).all()
    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()

    return templates.TemplateResponse(
        "admin/computers.html",
        context_with_defaults(
            request,
            current_user,
            {
                "computers": computers,
                "users": users,
                "message": message,
                "search": q,
                "location_filter": location,
                "rtc_filter": rtc,
                "owner_filter": owner_id,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "page": page,
                "total_pages": total_pages,
                "total_count": total_count,
            },
        ),
    )


@router.get("/computers/create", response_class=HTMLResponse)
def create_computer_form(request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()
    return templates.TemplateResponse(
        "admin/computer_form.html",
        context_with_defaults(request, current_user, {"edit_computer": None, "users": users}),
    )


@router.post("/computers/create")
def create_computer(
    request: Request,
    hostname: str = Form(...),
    ip: str | None = Form(None),
    mac: str | None = Form(None),
    os: str | None = Form(None),
    location: str | None = Form(None),
    owner_user_id: str | None = Form(None),
    last_maintenance_at: str | None = Form(None),
    is_round_the_clock: bool | None = Form(False),
    notes: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()

    # Validations
    if not validate_ip(ip):
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(
                request, current_user, {"edit_computer": None, "users": users, "error": "Некорректный IP-адрес."}
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not validate_mac(mac):
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(
                request,
                current_user,
                {"edit_computer": None, "users": users, "error": "Некорректный MAC-адрес (формат AA:BB:CC:DD:EE:FF)."},
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing = db.query(Computer).filter(func.lower(Computer.hostname) == hostname.strip().lower()).first()
    if existing:
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(
                request,
                current_user,
                {"edit_computer": None, "users": users, "error": "Компьютер с таким именем уже существует."},
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    parsed_last_maint = None
    if last_maintenance_at and last_maintenance_at.strip():
        try:
            maint_date = date.fromisoformat(last_maintenance_at.strip())
            today = datetime.now(timezone.utc).date()
            if maint_date > today:
                return templates.TemplateResponse(
                    "admin/computer_form.html",
                    context_with_defaults(
                        request,
                        current_user,
                        {
                            "edit_computer": None,
                            "users": users,
                            "error": "Дата последнего обслуживания не может быть в будущем.",
                        },
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            if maint_date < date(2000, 1, 1):
                return templates.TemplateResponse(
                    "admin/computer_form.html",
                    context_with_defaults(
                        request,
                        current_user,
                        {
                            "edit_computer": None,
                            "users": users,
                            "error": "Дата последнего обслуживания не может быть ранее 01.01.2000.",
                        },
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            parsed_last_maint = datetime.combine(maint_date, datetime.min.time())
        except ValueError:
            return templates.TemplateResponse(
                "admin/computer_form.html",
                context_with_defaults(
                    request,
                    current_user,
                    {"edit_computer": None, "users": users, "error": "Некорректный формат даты."},
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    parsed_owner_id = int(owner_user_id) if owner_user_id and owner_user_id.isdigit() else None

    computer = Computer(
        hostname=hostname.strip(),
        ip=ip.strip() if ip else None,
        mac=mac.strip() if mac else None,
        os=os.strip() if os else None,
        location=location.strip() if location else None,
        owner_user_id=parsed_owner_id,
        is_round_the_clock=bool(is_round_the_clock),
        last_maintenance_at=parsed_last_maint,
        notes=notes.strip() if notes else None,
        status="active",
    )

    from app.services.scheduling_service import compute_next_maintenance_due_at

    due_d = compute_next_maintenance_due_at(computer, db)
    computer.next_maintenance_due_at = datetime.combine(due_d, datetime.min.time())

    db.add(computer)
    db.commit()
    db.refresh(computer)

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="create_computer",
        entity="computers",
        entity_id=computer.id,
        after={
            "hostname": computer.hostname,
            "ip": computer.ip,
            "owner_user_id": computer.owner_user_id,
            "is_round_the_clock": computer.is_round_the_clock,
            "last_maintenance_at": computer.last_maintenance_at.isoformat() if computer.last_maintenance_at else None,
            "next_maintenance_due_at": computer.next_maintenance_due_at.isoformat()
            if computer.next_maintenance_due_at
            else None,
        },
    )

    return RedirectResponse(
        url="/admin/computers?message=Компьютер+успешно+добавлен", status_code=status.HTTP_302_FOUND
    )


@router.get("/computers/{computer_id}/edit", response_class=HTMLResponse)
def edit_computer_form(
    computer_id: int, request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return RedirectResponse(url="/admin/computers", status_code=status.HTTP_302_FOUND)

    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()
    return templates.TemplateResponse(
        "admin/computer_form.html",
        context_with_defaults(request, current_user, {"edit_computer": computer, "users": users}),
    )


@router.post("/computers/{computer_id}/edit")
def update_computer(
    computer_id: int,
    request: Request,
    hostname: str = Form(...),
    ip: str | None = Form(None),
    mac: str | None = Form(None),
    os: str | None = Form(None),
    location: str | None = Form(None),
    owner_user_id: str | None = Form(None),
    last_maintenance_at: str | None = Form(None),
    is_round_the_clock: bool | None = Form(False),
    notes: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return RedirectResponse(url="/admin/computers", status_code=status.HTTP_302_FOUND)

    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()

    if not validate_ip(ip):
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(
                request, current_user, {"edit_computer": computer, "users": users, "error": "Некорректный IP-адрес."}
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not validate_mac(mac):
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(
                request, current_user, {"edit_computer": computer, "users": users, "error": "Некорректный MAC-адрес."}
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    from datetime import datetime, timezone

    parsed_last_maint = None
    if last_maintenance_at and last_maintenance_at.strip():
        try:
            maint_date = date.fromisoformat(last_maintenance_at.strip())
            today = datetime.now(timezone.utc).date()
            if maint_date > today:
                return templates.TemplateResponse(
                    "admin/computer_form.html",
                    context_with_defaults(
                        request,
                        current_user,
                        {
                            "edit_computer": computer,
                            "users": users,
                            "error": "Дата последнего обслуживания не может быть в будущем.",
                        },
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            if maint_date < date(2000, 1, 1):
                return templates.TemplateResponse(
                    "admin/computer_form.html",
                    context_with_defaults(
                        request,
                        current_user,
                        {
                            "edit_computer": computer,
                            "users": users,
                            "error": "Дата последнего обслуживания не может быть ранее 01.01.2000.",
                        },
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            parsed_last_maint = datetime.combine(maint_date, datetime.min.time())
        except ValueError:
            return templates.TemplateResponse(
                "admin/computer_form.html",
                context_with_defaults(
                    request,
                    current_user,
                    {"edit_computer": computer, "users": users, "error": "Некорректный формат даты."},
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    before_state = {
        "hostname": computer.hostname,
        "ip": computer.ip,
        "mac": computer.mac,
        "os": computer.os,
        "location": computer.location,
        "owner_user_id": computer.owner_user_id,
        "is_round_the_clock": computer.is_round_the_clock,
        "last_maintenance_at": computer.last_maintenance_at.isoformat() if computer.last_maintenance_at else None,
        "next_maintenance_due_at": computer.next_maintenance_due_at.isoformat()
        if computer.next_maintenance_due_at
        else None,
    }

    parsed_owner_id = int(owner_user_id) if owner_user_id and owner_user_id.isdigit() else None

    computer.hostname = hostname.strip()
    computer.ip = ip.strip() if ip else None
    computer.mac = mac.strip() if mac else None
    computer.os = os.strip() if os else None
    computer.location = location.strip() if location else None
    computer.owner_user_id = parsed_owner_id
    computer.is_round_the_clock = bool(is_round_the_clock)
    computer.last_maintenance_at = parsed_last_maint
    computer.notes = notes.strip() if notes else None

    from app.services.scheduling_service import compute_next_maintenance_due_at

    due_d = compute_next_maintenance_due_at(computer, db)
    computer.next_maintenance_due_at = datetime.combine(due_d, datetime.min.time())

    db.commit()

    after_state = {
        "hostname": computer.hostname,
        "ip": computer.ip,
        "mac": computer.mac,
        "os": computer.os,
        "location": computer.location,
        "owner_user_id": computer.owner_user_id,
        "is_round_the_clock": computer.is_round_the_clock,
        "last_maintenance_at": computer.last_maintenance_at.isoformat() if computer.last_maintenance_at else None,
        "next_maintenance_due_at": computer.next_maintenance_due_at.isoformat()
        if computer.next_maintenance_due_at
        else None,
    }

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="update_computer",
        entity="computers",
        entity_id=computer.id,
        before=before_state,
        after=after_state,
    )

    return RedirectResponse(
        url="/admin/computers?message=Данные+компьютера+обновлены", status_code=status.HTTP_302_FOUND
    )


@router.post("/computers/{computer_id}/delete")
def delete_computer(computer_id: int, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if computer:
        before_state = {"hostname": computer.hostname, "ip": computer.ip, "owner_user_id": computer.owner_user_id}
        db.delete(computer)
        db.commit()

        log_audit(
            db=db,
            actor_user_id=current_user.id,
            action="delete_computer",
            entity="computers",
            entity_id=computer_id,
            before=before_state,
        )

    return RedirectResponse(url="/admin/computers?message=Компьютер+удален", status_code=status.HTTP_302_FOUND)


@router.get("/docs/fleet-import-format", response_class=HTMLResponse)
def admin_fleet_import_doc(request: Request, current_user: User = Depends(require_admin)):
    from app.importer.schema import FLEET_IMPORT_COLUMNS

    return templates.TemplateResponse(
        "admin/doc_import.html",
        context_with_defaults(request, current_user, {"columns": FLEET_IMPORT_COLUMNS}),
    )


@router.post("/seed-e2e")
def trigger_e2e_seed(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.seed_e2e import seed_e2e

    return seed_e2e(db)


DEFAULT_SETTINGS = {
    "interval_rtc_months": 6,
    "interval_non_rtc_months": 12,
    "selection_window_days": 20,
    "prompt_start_offset_days": 10,
    "technician_daily_capacity": 1,
    "allow_short_days": True,
    "timezone": "Europe/Minsk",
}


def get_all_app_settings(db: Session) -> dict[str, Any]:
    current = dict(DEFAULT_SETTINGS)
    setting_row = db.query(Setting).filter(Setting.key == "app_settings").first()
    if setting_row and isinstance(setting_row.value_json, dict):
        current.update(setting_row.value_json)
    return current


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    current_settings = get_all_app_settings(db)
    return templates.TemplateResponse(
        "admin/settings.html",
        context_with_defaults(
            request,
            current_user,
            {"settings": current_settings, "message": message, "error": error},
        ),
    )


@router.post("/settings")
def update_settings(
    request: Request,
    interval_rtc_months: int = Form(...),
    interval_non_rtc_months: int = Form(...),
    selection_window_days: int = Form(...),
    prompt_start_offset_days: int = Form(...),
    technician_daily_capacity: int = Form(...),
    allow_short_days: bool | None = Form(False),
    timezone_str: str = Form("Europe/Minsk", alias="timezone"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    errors = []
    if interval_rtc_months <= 0:
        errors.append("Интервал ТО для 24/7 ПК должен быть больше 0.")
    if interval_non_rtc_months <= 0:
        errors.append("Интервал ТО для обычных ПК должен быть больше 0.")
    if selection_window_days <= 0:
        errors.append("Ширина окна выбора должна быть больше 0.")
    if not (0 <= prompt_start_offset_days <= selection_window_days):
        errors.append("Смещение начала напоминаний должно быть в пределах 0..selection_window_days.")
    if technician_daily_capacity <= 0:
        errors.append("Дневная норма техника должна быть больше 0.")

    if errors:
        current_settings = get_all_app_settings(db)
        return templates.TemplateResponse(
            "admin/settings.html",
            context_with_defaults(
                request,
                current_user,
                {"settings": current_settings, "error": "; ".join(errors)},
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    before_settings = get_all_app_settings(db)
    new_settings = {
        "interval_rtc_months": interval_rtc_months,
        "interval_non_rtc_months": interval_non_rtc_months,
        "selection_window_days": selection_window_days,
        "prompt_start_offset_days": prompt_start_offset_days,
        "technician_daily_capacity": technician_daily_capacity,
        "allow_short_days": bool(allow_short_days),
        "timezone": timezone_str.strip() or "Europe/Minsk",
    }

    row = db.query(Setting).filter(Setting.key == "app_settings").first()
    if row:
        row.value_json = new_settings
    else:
        row = Setting(key="app_settings", value_json=new_settings)
        db.add(row)

    for k, v in new_settings.items():
        s_item = db.query(Setting).filter(Setting.key == k).first()
        if s_item:
            s_item.value_json = v
        else:
            db.add(Setting(key=k, value_json=v))

    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="update_settings",
        entity="settings",
        before=before_settings,
        after=new_settings,
    )

    return RedirectResponse(
        url="/admin/settings?message=Настройки+успешно+сохранены", status_code=status.HTTP_302_FOUND
    )


@router.post("/settings/reset")
def reset_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    before_settings = get_all_app_settings(db)

    row = db.query(Setting).filter(Setting.key == "app_settings").first()
    if row:
        row.value_json = dict(DEFAULT_SETTINGS)
    else:
        db.add(Setting(key="app_settings", value_json=dict(DEFAULT_SETTINGS)))

    for k, v in DEFAULT_SETTINGS.items():
        s_item = db.query(Setting).filter(Setting.key == k).first()
        if s_item:
            s_item.value_json = v
        else:
            db.add(Setting(key=k, value_json=v))

    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="reset_settings",
        entity="settings",
        before=before_settings,
        after=dict(DEFAULT_SETTINGS),
    )

    return RedirectResponse(
        url="/admin/settings?message=Настройки+сброшены+к+значениям+по+умолчанию",
        status_code=status.HTTP_302_FOUND,
    )


# --- PROTOCOL EDITOR ---


@router.get("/protocol", response_class=HTMLResponse)
def list_protocol_items(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    items = db.query(MaintenanceProtocolItem).order_by(MaintenanceProtocolItem.order_index.asc()).all()
    return templates.TemplateResponse(
        "admin/protocol.html",
        context_with_defaults(request, current_user, {"items": items, "message": message, "error": error}),
    )


@router.post("/protocol/create")
def create_protocol_item(
    request: Request,
    title_ru: str = Form(...),
    title_en: str = Form(...),
    description: str | None = Form(None),
    is_active: bool | None = Form(True),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    title_ru_str = parse_optional_str(title_ru)
    title_en_str = parse_optional_str(title_en)

    if not title_ru_str or not title_en_str:
        items = db.query(MaintenanceProtocolItem).order_by(MaintenanceProtocolItem.order_index.asc()).all()
        return templates.TemplateResponse(
            "admin/protocol.html",
            context_with_defaults(
                request,
                current_user,
                {"items": items, "error": "Названия на русском и английском языках обязательны."},
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    max_idx = db.query(func.max(MaintenanceProtocolItem.order_index)).scalar()
    next_idx = (max_idx + 1) if max_idx is not None else 0

    item = MaintenanceProtocolItem(
        order_index=next_idx,
        title_ru=title_ru_str,
        title_en=title_en_str,
        description=parse_optional_str(description),
        is_active=bool(is_active),
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="create_protocol_item",
        entity="maintenance_protocol_items",
        entity_id=item.id,
        after={"title_ru": item.title_ru, "title_en": item.title_en, "order_index": item.order_index},
    )

    return RedirectResponse(
        url="/admin/protocol?message=Пункт+протокола+успешно+добавлен", status_code=status.HTTP_302_FOUND
    )


@router.post("/protocol/{item_id}/edit")
def update_protocol_item(
    item_id: int,
    request: Request,
    title_ru: str = Form(...),
    title_en: str = Form(...),
    description: str | None = Form(None),
    is_active: bool | None = Form(False),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.id == item_id).first()
    if not item:
        return RedirectResponse(url="/admin/protocol", status_code=status.HTTP_302_FOUND)

    title_ru_str = parse_optional_str(title_ru)
    title_en_str = parse_optional_str(title_en)

    if not title_ru_str or not title_en_str:
        items = db.query(MaintenanceProtocolItem).order_by(MaintenanceProtocolItem.order_index.asc()).all()
        return templates.TemplateResponse(
            "admin/protocol.html",
            context_with_defaults(
                request,
                current_user,
                {"items": items, "error": "Названия на русском и английском языках обязательны."},
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    before_state = {
        "title_ru": item.title_ru,
        "title_en": item.title_en,
        "is_active": item.is_active,
    }

    item.title_ru = title_ru_str
    item.title_en = title_en_str
    item.description = parse_optional_str(description)
    item.is_active = bool(is_active)
    item.updated_at = datetime.now(timezone.utc)

    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="update_protocol_item",
        entity="maintenance_protocol_items",
        entity_id=item.id,
        before=before_state,
        after={"title_ru": item.title_ru, "title_en": item.title_en, "is_active": item.is_active},
    )

    return RedirectResponse(url="/admin/protocol?message=Пункт+протокола+обновлен", status_code=status.HTTP_302_FOUND)


@router.post("/protocol/{item_id}/toggle")
def toggle_protocol_item(item_id: int, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.id == item_id).first()
    if item:
        before_val = item.is_active
        item.is_active = not item.is_active
        item.updated_at = datetime.now(timezone.utc)
        db.commit()

        log_audit(
            db=db,
            actor_user_id=current_user.id,
            action="toggle_protocol_item",
            entity="maintenance_protocol_items",
            entity_id=item.id,
            before={"is_active": before_val},
            after={"is_active": item.is_active},
        )

    return RedirectResponse(url="/admin/protocol", status_code=status.HTTP_302_FOUND)


@router.post("/protocol/{item_id}/delete")
def delete_protocol_item(
    item_id: int, request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    item = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.id == item_id).first()
    if not item:
        return RedirectResponse(url="/admin/protocol", status_code=status.HTTP_302_FOUND)

    from app.models.models import MaintenanceEventCheck

    ref_count = (
        db.query(func.count(MaintenanceEventCheck.id))
        .filter(MaintenanceEventCheck.protocol_item_id == item.id)
        .scalar()
        or 0
    )
    if ref_count > 0:
        items = db.query(MaintenanceProtocolItem).order_by(MaintenanceProtocolItem.order_index.asc()).all()
        return templates.TemplateResponse(
            "admin/protocol.html",
            context_with_defaults(
                request,
                current_user,
                {
                    "items": items,
                    "error": "Пункт используется в проведенных ТО. Вы можете деактивировать его вместо удаления.",
                },
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    before_state = {"title_ru": item.title_ru, "order_index": item.order_index}
    db.delete(item)
    db.commit()

    remaining = db.query(MaintenanceProtocolItem).order_by(MaintenanceProtocolItem.order_index.asc()).all()
    for idx, rem_item in enumerate(remaining):
        rem_item.order_index = idx
    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="delete_protocol_item",
        entity="maintenance_protocol_items",
        entity_id=item_id,
        before=before_state,
    )

    return RedirectResponse(url="/admin/protocol?message=Пункт+протокола+удален", status_code=status.HTTP_302_FOUND)


@router.post("/protocol/reorder")
def reorder_protocol_items(
    item_ids: list[int] = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    for new_idx, item_id in enumerate(item_ids):
        item = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.id == item_id).first()
        if item:
            item.order_index = new_idx
    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="reorder_protocol_items",
        entity="maintenance_protocol_items",
        after={"item_ids_order": item_ids},
    )

    return RedirectResponse(url="/admin/protocol?message=Порядок+пунктов+обновлен", status_code=status.HTTP_302_FOUND)


# --- WORKING CALENDAR EDITOR ---


@router.get("/calendar", response_class=HTMLResponse)
def calendar_editor_page(
    request: Request,
    year: Any = Query(None),
    month: Any = Query(None),
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    now_d = datetime.now(timezone.utc).date()
    parsed_year = parse_optional_int(year) or now_d.year
    parsed_month = parse_optional_int(month) or now_d.month

    from app.core.i18n import get_locale
    from app.services.scheduling_service import get_month_calendar_grid

    grid = get_month_calendar_grid(parsed_year, parsed_month, db, current_date=now_d)
    locale_str = get_locale(request, current_user.locale)

    if locale_str == "en":
        weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        month_names = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
    else:
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        month_names = [
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь",
        ]

    month_name = month_names[grid["month"] - 1]

    return templates.TemplateResponse(
        "admin/calendar.html",
        context_with_defaults(
            request,
            current_user,
            {
                "weeks": grid["weeks"],
                "year": grid["year"],
                "month": grid["month"],
                "month_name": month_name,
                "prev_year": grid["prev_year"],
                "prev_month": grid["prev_month"],
                "next_year": grid["next_year"],
                "next_month": grid["next_month"],
                "min_year": grid["min_year"],
                "max_year": grid["max_year"],
                "weekday_names": weekday_names,
                "message": message,
                "error": error,
            },
        ),
    )


@router.post("/calendar/toggle")
def toggle_calendar_day(
    target_date_str: str = Form(..., alias="date"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from datetime import date as py_date

    try:
        c_date = py_date.fromisoformat(target_date_str.strip())
    except ValueError:
        return RedirectResponse(url="/admin/calendar?error=Некорректная+дата", status_code=status.HTTP_302_FOUND)

    entry = db.query(WorkingCalendar).filter(WorkingCalendar.date == c_date).first()
    before_state = None

    if entry:
        before_state = {
            "is_working": entry.is_working,
            "kind": entry.kind.value if hasattr(entry.kind, "value") else str(entry.kind),
        }
        entry.is_working = not entry.is_working
        if entry.is_working:
            entry.kind = DayKind.WORKDAY
        else:
            entry.kind = DayKind.WEEKEND if c_date.weekday() >= 5 else DayKind.HOLIDAY
        entry.source = "admin"
    else:
        is_w = not (c_date.weekday() >= 5)
        new_is_w = not is_w
        k = DayKind.WORKDAY if new_is_w else (DayKind.WEEKEND if c_date.weekday() >= 5 else DayKind.HOLIDAY)
        entry = WorkingCalendar(date=c_date, is_working=new_is_w, kind=k, source="admin")
        db.add(entry)

    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="toggle_calendar_day",
        entity="working_calendar",
        before=before_state,
        after={"date": c_date.isoformat(), "is_working": entry.is_working, "kind": entry.kind.value},
    )

    return RedirectResponse(
        url=f"/admin/calendar?year={c_date.year}&month={c_date.month}&message=Статус+дня+обновлен",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/calendar/edit-day")
def edit_calendar_day(
    target_date_str: str = Form(..., alias="date"),
    kind: str = Form(...),
    description: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from datetime import date as py_date

    try:
        c_date = py_date.fromisoformat(target_date_str.strip())
    except ValueError:
        return RedirectResponse(url="/admin/calendar?error=Некорректная+дата", status_code=status.HTTP_302_FOUND)

    parsed_kind = parse_optional_enum(kind, DayKind)
    if not parsed_kind:
        return RedirectResponse(url="/admin/calendar?error=Некорректный+тип+дня", status_code=status.HTTP_302_FOUND)

    is_w = parsed_kind in (DayKind.WORKDAY, DayKind.SHORT_DAY)

    entry = db.query(WorkingCalendar).filter(WorkingCalendar.date == c_date).first()
    before_state = {"kind": entry.kind.value, "is_working": entry.is_working} if entry else None

    if entry:
        entry.kind = parsed_kind
        entry.is_working = is_w
        entry.description = parse_optional_str(description)
        entry.source = "admin"
    else:
        entry = WorkingCalendar(
            date=c_date,
            kind=parsed_kind,
            is_working=is_w,
            description=parse_optional_str(description),
            source="admin",
        )
        db.add(entry)

    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="edit_calendar_day",
        entity="working_calendar",
        before=before_state,
        after={"date": c_date.isoformat(), "kind": parsed_kind.value, "is_working": is_w},
    )

    return RedirectResponse(
        url=f"/admin/calendar?year={c_date.year}&month={c_date.month}&message=Параметры+дня+обновлены",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/calendar/import/template.csv")
def download_calendar_template_csv(current_user: User = Depends(require_admin)):
    from app.importer.calendar_import import generate_calendar_template_csv

    content = generate_calendar_template_csv()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="calendar_template.csv"'},
    )


@router.get("/calendar/import/template.json")
def download_calendar_template_json(current_user: User = Depends(require_admin)):
    from app.importer.calendar_import import generate_calendar_template_json

    content = generate_calendar_template_json()
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="calendar_template.json"'},
    )


@router.post("/calendar/bulk-import")
async def bulk_import_calendar(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from datetime import date as py_date

    content_bytes = await file.read()
    filename = file.filename.lower()

    parsed_rows = []
    errors = []

    if filename.endswith(".json"):
        import json

        try:
            data = json.loads(content_bytes.decode("utf-8"))
            if not isinstance(data, list):
                errors.append("JSON должен содержать массив объектов.")
            else:
                for idx, item in enumerate(data, start=1):
                    if not isinstance(item, dict) or "date" not in item:
                        errors.append(f"Запись #{idx}: отсутствует поле 'date'.")
                        continue
                    try:
                        d_val = py_date.fromisoformat(str(item["date"]).strip())
                        k_str = str(item.get("kind", "workday")).strip()
                        k_enum = parse_optional_enum(k_str, DayKind) or DayKind.WORKDAY
                        is_w = bool(item.get("is_working", k_enum in (DayKind.WORKDAY, DayKind.SHORT_DAY)))
                        desc = str(item.get("description", "")).strip() or None
                        parsed_rows.append({"date": d_val, "kind": k_enum, "is_working": is_w, "description": desc})
                    except ValueError:
                        errors.append(f"Запись #{idx}: некорректная дата '{item.get('date')}'.")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Ошибка чтения JSON файла: {exc}")

    elif filename.endswith(".csv"):
        import csv
        import io

        try:
            reader = csv.DictReader(io.StringIO(content_bytes.decode("utf-8")))
            for idx, row in enumerate(reader, start=2):
                if not row or not row.get("date"):
                    continue
                try:
                    d_val = py_date.fromisoformat(row["date"].strip())
                    k_str = (row.get("kind") or "workday").strip()
                    k_enum = parse_optional_enum(k_str, DayKind) or DayKind.WORKDAY
                    is_w = (
                        row.get("is_working", "").strip().lower() in ("1", "true", "да", "yes")
                        if "is_working" in row
                        else (k_enum in (DayKind.WORKDAY, DayKind.SHORT_DAY))
                    )
                    desc = (row.get("description") or "").strip() or None
                    parsed_rows.append({"date": d_val, "kind": k_enum, "is_working": is_w, "description": desc})
                except ValueError:
                    errors.append(f"Строка #{idx}: некорректная дата '{row.get('date')}'.")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Ошибка чтения CSV файла: {exc}")

    else:
        errors.append("Пожалуйста, загрузите файл формата .csv или .json.")

    if errors or not parsed_rows:
        now_d = datetime.now(timezone.utc).date()
        return RedirectResponse(
            url=f"/admin/calendar?year={now_d.year}&month={now_d.month}&error={errors[0] if errors else 'Файл+пуст'}",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        with db.begin_nested():
            for r in parsed_rows:
                entry = db.query(WorkingCalendar).filter(WorkingCalendar.date == r["date"]).first()
                if entry:
                    entry.kind = r["kind"]
                    entry.is_working = r["is_working"]
                    entry.description = r["description"]
                    entry.source = "admin"
                else:
                    db.add(
                        WorkingCalendar(
                            date=r["date"],
                            kind=r["kind"],
                            is_working=r["is_working"],
                            description=r["description"],
                            source="admin",
                        )
                    )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return RedirectResponse(
            url=f"/admin/calendar?error=Ошибка+при+импорте:+{exc}", status_code=status.HTTP_302_FOUND
        )

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="bulk_import_calendar",
        entity="working_calendar",
        after={"imported_count": len(parsed_rows), "filename": file.filename},
    )

    first_d = parsed_rows[0]["date"]
    return RedirectResponse(
        url=f"/admin/calendar?year={first_d.year}&month={first_d.month}&message=Импортировано+{len(parsed_rows)}+записей+календаря",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/calendar/reset")
def reset_calendar(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.services.scheduling_service import generate_calendar_seed_data

    seed_records = generate_calendar_seed_data()

    with db.begin_nested():
        for r in seed_records:
            entry = db.query(WorkingCalendar).filter(WorkingCalendar.date == r["date"]).first()
            kind_enum = parse_optional_enum(r["kind"], DayKind) or DayKind.WORKDAY
            if entry:
                entry.is_working = r["is_working"]
                entry.kind = kind_enum
                entry.description = r["description"]
                entry.source = "seed"
            else:
                db.add(
                    WorkingCalendar(
                        date=r["date"],
                        is_working=r["is_working"],
                        kind=kind_enum,
                        description=r["description"],
                        source="seed",
                    )
                )
    db.commit()

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="reset_calendar",
        entity="working_calendar",
        after={"message": "Calendar reset to Belarus defaults for 2025-2026"},
    )

    now_d = datetime.now(timezone.utc).date()
    return RedirectResponse(
        url=f"/admin/calendar?year={now_d.year}&month={now_d.month}&message=Календарь+сброшен+к+производственному+календарю+РБ",
        status_code=status.HTTP_302_FOUND,
    )


# --- AUDIT LOG VIEWER ---


@router.get("/audit", response_class=HTMLResponse)
def list_audit_logs(
    request: Request,
    q: Any = Query(None),
    entity: Any = Query(None),
    action: Any = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)

    q_str = parse_optional_str(q)
    if q_str:
        search_term = f"%{q_str.lower()}%"
        query = query.filter(
            (func.lower(AuditLog.action).like(search_term)) | (func.lower(AuditLog.entity).like(search_term))
        )

    entity_str = parse_optional_str(entity)
    if entity_str:
        query = query.filter(func.lower(AuditLog.entity) == entity_str.lower())

    action_str = parse_optional_str(action)
    if action_str:
        query = query.filter(func.lower(AuditLog.action) == action_str.lower())

    query = query.order_by(AuditLog.id.desc())

    total_count = query.count()
    total_pages = max(1, ceil(total_count / per_page))
    page = min(page, total_pages)

    logs = query.offset((page - 1) * per_page).limit(per_page).all()

    return templates.TemplateResponse(
        "admin/audit.html",
        context_with_defaults(
            request,
            current_user,
            {
                "logs": logs,
                "search": q,
                "entity_filter": entity,
                "action_filter": action,
                "page": page,
                "total_pages": total_pages,
                "total_count": total_count,
            },
        ),
    )
