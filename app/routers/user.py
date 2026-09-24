"""User routes for CFMS (Iteration 4 + Defect 8 fixes)."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.i18n import get_locale
from app.models.models import Computer, MaintenanceEvent, MaintenanceEventStatus, User, UserRole
from app.routers.web import context_with_defaults
from app.services.scheduling_service import (
    compute_next_maintenance_due_at,
    compute_window_bounds,
    get_available_dates,
    get_window_calendar_days,
    schedule_maintenance,
    validate_maintenance_date,
)

router = APIRouter(prefix="/user", tags=["user"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/my-computers", response_class=HTMLResponse)
def user_computers_page(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Page listing user's computers with primary date picker and selection window state."""
    if current_user.role == UserRole.ADMIN:
        computers = db.query(Computer).all()
    else:
        computers = db.query(Computer).filter(Computer.owner_user_id == current_user.id).all()

    computers_data = []
    today = datetime.now(timezone.utc).date()

    for comp in computers:
        if not comp.next_maintenance_due_at:
            comp.next_maintenance_due_at = compute_next_maintenance_due_at(comp, db)
            db.add(comp)

        due_date = (
            comp.next_maintenance_due_at.date()
            if isinstance(comp.next_maintenance_due_at, datetime)
            else comp.next_maintenance_due_at
        )

        window_start, window_end, prompt_start_date = compute_window_bounds(due_date, db)

        if today < prompt_start_date:
            window_state = "future"
        elif prompt_start_date <= today <= window_end:
            window_state = "active"
        else:
            window_state = "expired"

        # Get planned event if any
        planned_event = (
            db.query(MaintenanceEvent)
            .filter(MaintenanceEvent.computer_id == comp.id, MaintenanceEvent.status == MaintenanceEventStatus.PLANNED)
            .first()
        )

        active_locale = get_locale(request, current_user.locale)
        window_calendar = get_window_calendar_days(comp.id, db, today=today, locale=active_locale)

        # Get past maintenance events with details
        past_events = (
            db.query(MaintenanceEvent)
            .filter(
                MaintenanceEvent.computer_id == comp.id,
                MaintenanceEvent.status.in_(
                    [MaintenanceEventStatus.DONE, MaintenanceEventStatus.MISSED, MaintenanceEventStatus.CANCELLED]
                ),
            )
            .order_by(MaintenanceEvent.scheduled_date.desc())
            .all()
        )

        computers_data.append(
            {
                "computer": comp,
                "due_date": due_date,
                "prompt_start_date": prompt_start_date,
                "window_start": window_start,
                "window_end": window_end,
                "window_state": window_state,
                "window_open": window_state == "active",
                "planned_event": planned_event,
                "window_calendar": window_calendar,
                "available_dates": window_calendar["days"],
                "past_events": past_events,
                "is_manager": len(computers) > 1,
            }
        )

    db.commit()

    return templates.TemplateResponse(
        "user_computers.html",
        context_with_defaults(
            request,
            current_user,
            {
                "computers_data": computers_data,
                "message": message,
                "error": error,
                "is_manager_user": len(computers) > 1,
            },
        ),
    )


@router.get("/my-computers/{computer_id}", response_class=HTMLResponse)
def user_computer_detail_page(
    computer_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detailed computer info route showing specs, last maintenance date, and full history with checklists."""
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return RedirectResponse(url="/user/my-computers?error=Компьютер+не+найден", status_code=status.HTTP_302_FOUND)

    if current_user.role != UserRole.ADMIN and computer.owner_user_id != current_user.id:
        return RedirectResponse(url="/user/my-computers?error=Доступ+запрещен", status_code=status.HTTP_302_FOUND)

    planned_event = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.computer_id == computer.id, MaintenanceEvent.status == MaintenanceEventStatus.PLANNED)
        .first()
    )

    past_events = (
        db.query(MaintenanceEvent)
        .filter(
            MaintenanceEvent.computer_id == computer.id,
            MaintenanceEvent.status.in_(
                [MaintenanceEventStatus.DONE, MaintenanceEventStatus.MISSED, MaintenanceEventStatus.CANCELLED]
            ),
        )
        .order_by(MaintenanceEvent.scheduled_date.desc())
        .all()
    )

    return templates.TemplateResponse(
        "user_computer_detail.html",
        context_with_defaults(
            request,
            current_user,
            {
                "computer": computer,
                "planned_event": planned_event,
                "past_events": past_events,
            },
        ),
    )


@router.get("/schedule/{computer_id}", response_class=HTMLResponse)
def schedule_date_picker_page(
    computer_id: int,
    request: Request,
    error: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fallback schedule page."""
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return RedirectResponse(url="/user/my-computers?error=Компьютер+не+найден", status_code=status.HTTP_302_FOUND)

    if current_user.role != UserRole.ADMIN and computer.owner_user_id != current_user.id:
        return RedirectResponse(url="/user/my-computers?error=Доступ+запрещен", status_code=status.HTTP_302_FOUND)

    available_dates = get_available_dates(computer.id, db)

    planned_event = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.computer_id == computer.id, MaintenanceEvent.status == MaintenanceEventStatus.PLANNED)
        .first()
    )

    return templates.TemplateResponse(
        "user_schedule.html",
        context_with_defaults(
            request,
            current_user,
            {
                "computer": computer,
                "available_dates": available_dates,
                "planned_event": planned_event,
                "error": error,
            },
        ),
    )


@router.post("/schedule/{computer_id}")
def submit_schedule_date(
    computer_id: int,
    scheduled_date_str: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit selected maintenance date for computer."""
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Компьютер не найден")

    if current_user.role != UserRole.ADMIN and computer.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен")

    try:
        selected_date = date.fromisoformat(scheduled_date_str.strip())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Некорректный формат даты")

    is_valid, err_msg = validate_maintenance_date(computer.id, selected_date, db)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err_msg)

    try:
        schedule_maintenance(computer.id, selected_date, current_user.id, db)
        return RedirectResponse(
            url="/user/my-computers?message=Дата+технического+обслуживания+успешно+запланирована",
            status_code=status.HTTP_302_FOUND,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
