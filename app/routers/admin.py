
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.auth.providers import LocalAuthProvider
from app.core.database import get_db
from app.models.models import Computer, User, UserRole
from app.routers.web import context_with_defaults
from app.services.audit_service import log_audit

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/admin", tags=["admin"])

# --- USERS CRUD ---

@router.get("/users", response_class=HTMLResponse)
def list_users(
    request: Request,
    message: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    users = db.query(User).order_by(User.id.asc()).all()
    return templates.TemplateResponse(
        "admin/users.html",
        context_with_defaults(request, current_user, {"users": users, "message": message})
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
        (User.username == username) | (User.email_or_login == email_or_login)
    ).first()
    if existing:
        return templates.TemplateResponse(
            "admin/user_form.html",
            context_with_defaults(request, current_user, {"edit_user": None, "error": "Пользователь с таким именем или email уже существует."}),
            status_code=status.HTTP_400_BAD_REQUEST
        )

    provider = LocalAuthProvider()
    hashed = provider.hash_password(password) if password else None

    user_role = UserRole(role) if role in [r.value for e, r in UserRole.__members__.items()] else UserRole.USER
    new_user = User(
        username=username,
        email_or_login=email_or_login,
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

    user.username = username
    user.email_or_login = email_or_login
    if password and password.strip():
        provider = LocalAuthProvider()
        user.password_hash = provider.hash_password(password)

    if role in [r.value for e, r in UserRole.__members__.items()]:
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

@router.post("/users/{user_id}/toggle-active")
def toggle_user_active(
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
            action="toggle_user_active",
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
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN).order_by(User.id.asc()).all()
    return templates.TemplateResponse(
        "admin/technicians.html",
        context_with_defaults(request, current_user, {"technicians": technicians})
    )

# --- COMPUTERS CRUD ---

@router.get("/computers", response_class=HTMLResponse)
def list_computers(
    request: Request,
    message: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    computers = db.query(Computer).order_by(Computer.id.asc()).all()
    return templates.TemplateResponse(
        "admin/computers.html",
        context_with_defaults(request, current_user, {"computers": computers, "message": message})
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
    existing = db.query(Computer).filter(Computer.hostname == hostname).first()
    if existing:
        users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()
        return templates.TemplateResponse(
            "admin/computer_form.html",
            context_with_defaults(request, current_user, {"edit_computer": None, "users": users, "error": "Компьютер с таким именем уже существует."}),
            status_code=status.HTTP_400_BAD_REQUEST
        )

    parsed_owner_id = int(owner_user_id) if owner_user_id and owner_user_id.isdigit() else None

    computer = Computer(
        hostname=hostname,
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

    computer.hostname = hostname
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
