from math import ceil

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_magic_link_token
from app.core.database import get_db
from app.core.validators import validate_ip, validate_mac
from app.models.models import Computer, Setting, User, UserRole
from app.routers.web import context_with_defaults
from app.services.audit_service import log_audit

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/admin", tags=["admin"])

# --- USERS CRUD ---

@router.get("/users", response_class=HTMLResponse)
def list_users(
    request: Request,
    q: str | None = Query(None),
    role: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    sort_by: str = Query("id"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    message: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    query = db.query(User)

    if q and q.strip():
        search_term = f"%{q.strip().lower()}%"
        query = query.filter((func.lower(User.username).like(search_term)) | (func.lower(User.email_or_login).like(search_term)))

    if role and role in [r.value for r in UserRole]:
        query = query.filter(User.role == UserRole(role))

    if status_filter == "active":
        query = query.filter(User.is_active == True)
    elif status_filter == "inactive":
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
        context_with_defaults(request, current_user, {
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
        })
    )

@router.get("/users/create", response_class=HTMLResponse)
def create_user_form(
    request: Request,
    current_user: User = Depends(require_admin)
):
    return templates.TemplateResponse(
        "admin/user_form.html",
        context_with_defaults(request, current_user, {"edit_user": None})
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
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter(
        (func.lower(User.username) == username.strip().lower())
        | (func.lower(User.email_or_login) == email_or_login.strip().lower())
    ).first()
    if existing:
        return templates.TemplateResponse(
            "admin/user_form.html",
            context_with_defaults(request, current_user, {"edit_user": None, "error": "Пользователь с таким именем или email уже существует."}),
            status_code=status.HTTP_400_BAD_REQUEST
        )

    provider = LocalAuthProvider()
    hashed = provider.hash_password(password) if password else None

    user_role = UserRole(role) if role in [r.value for r in UserRole] else UserRole.USER
    new_user = User(
        username=username.strip(),
        email_or_login=email_or_login.strip(),
        password_hash=hashed,
        role=user_role,
        is_active=bool(is_active)
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
        after={"username": new_user.username, "email_or_login": new_user.email_or_login, "role": new_user.role.value, "is_active": new_user.is_active}
    )

    return RedirectResponse(url="/admin/users?message=Пользователь+успешно+создан", status_code=status.HTTP_302_FOUND)

@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
def edit_user_form(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        "admin/user_form.html",
        context_with_defaults(request, current_user, {"edit_user": user})
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
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

    before_state = {"username": user.username, "email_or_login": user.email_or_login, "role": user.role.value, "is_active": user.is_active}

    user.username = username.strip()
    user.email_or_login = email_or_login.strip()
    if password and password.strip():
        provider = LocalAuthProvider()
        user.password_hash = provider.hash_password(password.strip())

    if role in [r.value for r in UserRole]:
        user.role = UserRole(role)
    user.is_active = bool(is_active)

    db.commit()

    after_state = {"username": user.username, "email_or_login": user.email_or_login, "role": user.role.value, "is_active": user.is_active}

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="update_user",
        entity="users",
        entity_id=user.id,
        before=before_state,
        after=after_state
    )

    return RedirectResponse(url="/admin/users?message=Данные+пользователя+обновлены", status_code=status.HTTP_302_FOUND)

@router.get("/users/{user_id}/reset-password", response_class=HTMLResponse)
def reset_password_form(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        "admin/reset_password.html",
        context_with_defaults(request, current_user, {"edit_user": user})
    )

@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    new_password: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        provider = LocalAuthProvider()
        user.password_hash = provider.hash_password(new_password.strip())
        db.commit()

        log_audit(
            db=db,
            actor_user_id=current_user.id,
            action="reset_password",
            entity="users",
            entity_id=user.id
        )

    return RedirectResponse(url="/admin/users?message=Пароль+сброшен", status_code=status.HTTP_302_FOUND)

@router.get("/users/{user_id}/magic-link", response_class=HTMLResponse)
def get_magic_link(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

    token = generate_magic_link_token(user.id)
    magic_url = f"{request.base_url}auth/magic-link?token={token}"

    return templates.TemplateResponse(
        "admin/magic_link.html",
        context_with_defaults(request, current_user, {"edit_user": user, "magic_url": magic_url})
    )

@router.post("/users/{user_id}/magic-link")
def reissue_magic_link(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        log_audit(
            db=db,
            actor_user_id=current_user.id,
            action="reissue_magic_link",
            entity="users",
            entity_id=user.id
        )
    return RedirectResponse(url=f"/admin/users/{user_id}/magic-link", status_code=status.HTTP_302_FOUND)

@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
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
            after={"is_active": user.is_active}
        )

    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

# --- TECHNICIANS MANAGEMENT ---

@router.get("/technicians", response_class=HTMLResponse)
def list_technicians(
    request: Request,
    message: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN).order_by(User.id.asc()).all()

    # Load daily capacity settings
    capacities = {}
    for tech in technicians:
        setting = db.query(Setting).filter(Setting.key == f"technician_capacity_{tech.id}").first()
        capacities[tech.id] = setting.value_json if setting else 1

    return templates.TemplateResponse(
        "admin/technicians.html",
        context_with_defaults(request, current_user, {"technicians": technicians, "capacities": capacities, "message": message})
    )

@router.post("/technicians/{tech_id}/capacity")
def set_technician_capacity(
    tech_id: int,
    daily_capacity: int = Form(1),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
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
        after={"capacity": max(1, daily_capacity)}
    )

    return RedirectResponse(url="/admin/technicians?message=Дневная+норма+обновлена", status_code=status.HTTP_302_FOUND)

# --- COMPUTERS CRUD ---

@router.get("/computers", response_class=HTMLResponse)
def list_computers(
    request: Request,
    q: str | None = Query(None),
    location: str | None = Query(None),
    rtc: str | None = Query(None),
    owner_id: int | None = Query(None),
    sort_by: str = Query("hostname"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    message: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Computer)

    if q and q.strip():
        search_term = f"%{q.strip().lower()}%"
        query = query.filter((func.lower(Computer.hostname).like(search_term)) | (func.lower(Computer.ip).like(search_term)))

    if location and location.strip():
        query = query.filter(func.lower(Computer.location).like(f"%{location.strip().lower()}%"))

    if rtc == "yes":
        query = query.filter(Computer.is_round_the_clock == True)
    elif rtc == "no":
        query = query.filter(Computer.is_round_the_clock == False)

    if owner_id:
        query = query.filter(Computer.owner_user_id == owner_id)

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
        context_with_defaults(request, current_user, {
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
        })
    )

@router.get("/computers/create", response_class=HTMLResponse)
def create_computer_form(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()
    return templates.TemplateResponse(
        "admin/computer_form.html",
        context_with_defaults(request, current_user, {"edit_computer": None, "users": users})
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
    is_round_the_clock: bool | None = Form(False),
    notes: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()

    # Validations
    if not validate_ip(ip):
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(request, current_user, {"edit_computer": None, "users": users, "error": "Некорректный IP-адрес."}),
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if not validate_mac(mac):
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(request, current_user, {"edit_computer": None, "users": users, "error": "Некорректный MAC-адрес (формат AA:BB:CC:DD:EE:FF)."}),
            status_code=status.HTTP_400_BAD_REQUEST
        )

    existing = db.query(Computer).filter(func.lower(Computer.hostname) == hostname.strip().lower()).first()
    if existing:
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(request, current_user, {"edit_computer": None, "users": users, "error": "Компьютер с таким именем уже существует."}),
            status_code=status.HTTP_400_BAD_REQUEST
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
        notes=notes.strip() if notes else None,
        status="active"
    )
    db.add(computer)
    db.commit()
    db.refresh(computer)

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="create_computer",
        entity="computers",
        entity_id=computer.id,
        after={"hostname": computer.hostname, "ip": computer.ip, "owner_user_id": computer.owner_user_id, "is_round_the_clock": computer.is_round_the_clock}
    )

    return RedirectResponse(url="/admin/computers?message=Компьютер+успешно+добавлен", status_code=status.HTTP_302_FOUND)

@router.get("/computers/{computer_id}/edit", response_class=HTMLResponse)
def edit_computer_form(
    computer_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return RedirectResponse(url="/admin/computers", status_code=status.HTTP_302_FOUND)

    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()
    return templates.TemplateResponse(
        "admin/computer_form.html",
        context_with_defaults(request, current_user, {"edit_computer": computer, "users": users})
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
    is_round_the_clock: bool | None = Form(False),
    notes: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return RedirectResponse(url="/admin/computers", status_code=status.HTTP_302_FOUND)

    users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()

    if not validate_ip(ip):
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(request, current_user, {"edit_computer": computer, "users": users, "error": "Некорректный IP-адрес."}),
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if not validate_mac(mac):
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(request, current_user, {"edit_computer": computer, "users": users, "error": "Некорректный MAC-адрес."}),
            status_code=status.HTTP_400_BAD_REQUEST
        )

    before_state = {
        "hostname": computer.hostname,
        "ip": computer.ip,
        "mac": computer.mac,
        "os": computer.os,
        "location": computer.location,
        "owner_user_id": computer.owner_user_id,
        "is_round_the_clock": computer.is_round_the_clock,
    }

    parsed_owner_id = int(owner_user_id) if owner_user_id and owner_user_id.isdigit() else None

    computer.hostname = hostname.strip()
    computer.ip = ip.strip() if ip else None
    computer.mac = mac.strip() if mac else None
    computer.os = os.strip() if os else None
    computer.location = location.strip() if location else None
    computer.owner_user_id = parsed_owner_id
    computer.is_round_the_clock = bool(is_round_the_clock)
    computer.notes = notes.strip() if notes else None

    db.commit()

    after_state = {
        "hostname": computer.hostname,
        "ip": computer.ip,
        "mac": computer.mac,
        "os": computer.os,
        "location": computer.location,
        "owner_user_id": computer.owner_user_id,
        "is_round_the_clock": computer.is_round_the_clock,
    }

    log_audit(
        db=db,
        actor_user_id=current_user.id,
        action="update_computer",
        entity="computers",
        entity_id=computer.id,
        before=before_state,
        after=after_state
    )

    return RedirectResponse(url="/admin/computers?message=Данные+компьютера+обновлены", status_code=status.HTTP_302_FOUND)

@router.post("/computers/{computer_id}/delete")
def delete_computer(
    computer_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
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
            before=before_state
        )

    return RedirectResponse(url="/admin/computers?message=Компьютер+удален", status_code=status.HTTP_302_FOUND)
